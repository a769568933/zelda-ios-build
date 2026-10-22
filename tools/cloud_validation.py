"""Private artifact intake for an ephemeral macOS validation job.

No application bytes or download credentials are committed or uploaded as
Actions artifacts. Only the job owns the intake private key. The report must
distinguish component checks from execution of a complete game on an iPhone.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = os.environ['GITHUB_RUN_ID']
PRIVATE = Path(os.environ['RUNNER_TEMP']).resolve() / ('candidate-private-' + RUN_ID)
REPORT = ROOT / 'build/candidate-validation'


def clean():
    if PRIVATE.parent != Path(os.environ['RUNNER_TEMP']).resolve() or not RUN_ID.isdecimal():
        raise ValueError('Invalid private validation directory')
    if PRIVATE.exists(): shutil.rmtree(PRIVATE)


def key():
    PRIVATE.mkdir(mode=0o700)
    pair = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    target = PRIVATE / 'intake.pem'
    target.write_bytes(pair.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    target.chmod(0o600)
    (ROOT / 'build').mkdir(exist_ok=True)
    (ROOT / 'build/candidate-intake-public.pem').write_bytes(pair.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def execute(command, *, cwd=ROOT, env=None, log):
    with (REPORT / log).open('w') as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    return result.returncode


def run():
    REPORT.mkdir(parents=True, exist_ok=True)
    report = dict(run_id=RUN_ID, platform=sys.platform,
                  packaged_cpu_checks_passed=False, baseline_reproduced=False,
                  sdk_simulator_checks_passed=False, full_game_execution_passed=False,
                  iphone_gpu_visuals_verified=False, native_60fps_verified=False)
    try:
        url = f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/main/cloud/inbox/{RUN_ID}.json"
        deadline = time.monotonic() + 1500
        envelope = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=20) as response: envelope = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code != 404: raise RuntimeError('Intake request failed') from None
            time.sleep(10)
        if envelope is None: raise RuntimeError('Timed out waiting for encrypted artifact intake')
        if envelope['run_id'] != RUN_ID: raise ValueError('Mismatched intake run')
        pair = serialization.load_pem_private_key((PRIVATE / 'intake.pem').read_bytes(), password=None)
        symmetric = pair.decrypt(base64.b64decode(envelope['wrapped_key']),
                                 padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        payload = json.loads(AESGCM(symmetric).decrypt(base64.b64decode(envelope['nonce']),
                             base64.b64decode(envelope['ciphertext']), RUN_ID.encode()))
        expected_tests = payload.get('expected_candidate_tests', 26)
        expected_failures = payload.get('baseline_expected_failures')
        if type(expected_tests) is not int or not 1 <= expected_tests <= 1000:
            raise ValueError('Invalid expected test count')
        if expected_failures is not None and (not isinstance(expected_failures, list)
                or not expected_failures or not all(isinstance(x, str) for x in expected_failures)):
            raise ValueError('Invalid baseline expectation')
        helper = ROOT / 'tools/library_helpers/library_file_transfer.py'
        paths = {}
        for entry in payload['inputs']:
            role = entry['role']
            if role not in ('candidate', 'baseline', 'tests') or role in paths: raise ValueError('Invalid validation role')
            target = PRIVATE / (role + ('.zip' if role == 'tests' else '.ipa'))
            result = subprocess.run([sys.executable, str(helper), 'materialize', str(target)],
                                    input=json.dumps(entry['transfer']), text=True, capture_output=True)
            if result.returncode: raise RuntimeError('Private artifact materialization failed: ' + role)
            digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
            if digest != entry['sha256']: raise ValueError('Private artifact hash mismatch: ' + role)
            paths[role] = target
            report[role + '_sha256'] = digest
        work = PRIVATE / 'tests'
        with zipfile.ZipFile(paths['tests']) as archive:
            for item in archive.infolist():
                resolved = (work / item.filename).resolve()
                if not resolved.is_relative_to(work.resolve()): raise ValueError('Invalid validation archive path')
            archive.extractall(work)
        base_env = dict(os.environ, ZELDA_ORIGINAL_IPA=str(paths['baseline']))
        for role in ('baseline', 'candidate'):
            output = PRIVATE / (role + '-cpu.json')
            env = dict(base_env, ZELDA_CPU_REPORT=str(output))
            code = execute([sys.executable, 'tools/test_candidate_cpu.py', str(paths[role])],
                           cwd=work, env=env, log=role + '-cpu.txt')
            details = json.loads(output.read_text())
            (REPORT / (role + '-cpu.json')).write_text(json.dumps(details, indent=2))
            if role == 'baseline':
                failures = details['failed']
                report['baseline_reproduced'] = (code == 1 and len(failures) == 3 and not details['errors']
                    and all('NativeStartupTests.' in name for name in failures))
                if expected_failures is not None:
                    report['baseline_reproduced'] = (code == 1 and sorted(failures) == sorted(expected_failures)
                        and details['tests_run'] == expected_tests and not details['errors'] and not details['skipped'])
            else:
                report['packaged_cpu_checks_passed'] = (code == 0 and details['tests_run'] == expected_tests
                    and not details['failed'] and not details['errors'] and not details['skipped'])
        # Rebuild the open-source module against the current Apple SDK and run
        # the actual simulator input host. This is separate from the game IPA.
        code = execute(['bash', 'tools/build_cloud.sh'], log='sdk-simulator.txt')
        report['sdk_simulator_checks_passed'] = code == 0
        if code == 0:
            report['simulator_result'] = json.loads((ROOT / 'build/simulator-result.json').read_text())
        report['component_validation_passed'] = all(report[k] for k in
            ('baseline_reproduced', 'packaged_cpu_checks_passed', 'sdk_simulator_checks_passed'))
        report['delivery_gate'] = 'blocked: full iPhone game execution and GPU validation unavailable'
    except Exception as error:
        # Never expose signed URLs, decrypted configuration or private paths.
        report['component_validation_passed'] = False
        report['failure_type'] = type(error).__name__
        print('Private candidate validation failed; inspect the sanitized report.')
    finally:
        (REPORT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    return 0 if report.get('component_validation_passed') else 1


if __name__ == '__main__':
    if sys.argv[1:] == ['key']: key()
    elif sys.argv[1:] == ['clean']: clean()
    elif sys.argv[1:] == ['run']: raise SystemExit(run())
    else: raise SystemExit('usage: cloud_validation.py key|run|clean')

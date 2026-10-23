#import <UIKit/UIKit.h>
#import <objc/message.h>
#include <stdint.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <math.h>
#include <unistd.h>
#include "front.h"

static uint64_t buttons;
static int32_t axes[4];
static unsigned oldInit, oldLayout, oldReset, checks;
static void check(BOOL ok, const char *message);
static uint64_t guestFrame;
uint64_t dm_guest_frame(void) { return guestFrame; }
static void poll(BOOL nextFrame) {
    if (nextFrame) guestFrame++;
    void (*fn)(void) = dlsym(RTLD_DEFAULT, "dm_phone_camera_poll");
    check(fn != NULL, "game input poll callback is exported");
    fn();
}
void dm_input_set(uint64_t b, int32_t lx, int32_t ly, int32_t rx, int32_t ry) {
    buttons = b; axes[0] = lx; axes[1] = ly; axes[2] = rx; axes[3] = ry;
}
void dm_touch_set(const dm_touch *touches, int count) { (void)touches; (void)count; }

// Exports mirror the original app; no game or private binary is in this test.
@interface DmGamepad : UIView
- (void)reset;
@end
@implementation DmGamepad
- (instancetype)initWithFrame:(CGRect)frame { oldInit++; return [super initWithFrame:frame]; }
- (void)layoutSubviews { oldLayout++; [super layoutSubviews]; }
- (void)reset { oldReset++; }
@end

@interface TestTouch : UITouch
@property(nonatomic) CGPoint point;
@end
@implementation TestTouch
- (CGPoint)locationInView:(UIView *)view { (void)view; return self.point; }
@end

@interface UIView (TestControls)
- (void)cameraFrame:(id)link;
- (void)reset;
@end

static void check(BOOL ok, const char *message) {
    checks++;
    if (!ok) { NSLog(@"[touch-test] FAIL: %s", message); exit(1); }
}
static TestTouch *finger(CGFloat x, CGFloat y) { TestTouch *t = [TestTouch new]; t.point = CGPointMake(x, y); return t; }
static void begin(UIView *v, TestTouch *t) { [v touchesBegan:[NSSet setWithObject:t] withEvent:nil]; }
static void move(UIView *v, TestTouch *t, CGFloat x, CGFloat y) { t.point = CGPointMake(x, y); [v touchesMoved:[NSSet setWithObject:t] withEvent:nil]; }
static void end(UIView *v, TestTouch *t) { [v touchesEnded:[NSSet setWithObject:t] withEvent:nil]; }

static void runTests(void) {
    DmGamepad *parent = [[DmGamepad alloc] initWithFrame:CGRectMake(0, 0, 874, 402)];
    [parent setNeedsLayout]; [parent layoutIfNeeded];
    check(oldInit == 0 && oldLayout == 0, "installer replaces original initialization and layout");
    check(parent.subviews.count == 1, "one replacement overlay");
    UIView *pad = parent.subviews.firstObject;
    check([NSStringFromClass(pad.class) isEqualToString:@"DmPhoneGamepad"], "replacement class loaded");
    check(CGRectEqualToRect(pad.bounds, parent.bounds), "overlay fills its container");
    check(pad.multipleTouchEnabled, "multitouch enabled");

    // Drain initialization resets before testing gesture ownership and host reset.
    dispatch_async(dispatch_get_main_queue(), ^{
        TestTouch *left = finger(6, 250); begin(pad, left);
        check(axes[0] == 0 && axes[1] == 0, "touch down is neutral");
        move(pad, left, 0, 250);
        check(axes[0] == -32767, "full left fits on screen at the extreme edge");
        end(pad, left); check(axes[0] == 0, "left release resets input");

        left = finger(130, 260); begin(pad, left); move(pad, left, 90, 260);
        check(axes[0] < 0, "floating movement away from the idle ring");
        TestTouch *camera = finger(500, 180); begin(pad, camera);
        check(axes[2] == 0 && axes[3] == 0, "camera touch down is neutral");
        move(pad, camera, 508, 172);
        check(axes[2] > 0 && axes[3] > 0, "right stick publishes its held displacement");
        poll(YES);
        check(axes[2] > 0 && axes[3] > 0 && axes[0] < 0, "move and camera run together");
        int32_t firstX = axes[2], firstY = axes[3];
        poll(NO); check(axes[2] == firstX && axes[3] == firstY, "repeated readers reuse one game-frame sample");
        poll(YES); check(axes[2] == firstX && axes[3] == firstY, "held right stick keeps turning at the same deflection");
        CGPoint (*rightPoint)(id, SEL) = (void *)objc_msgSend;
        CGPoint rightOrigin = rightPoint(pad, NSSelectorFromString(@"rightCentre"));
        move(pad, camera, 870, 180);
        check(CGPointEqualToPoint(rightOrigin, rightPoint(pad, NSSelectorFromString(@"rightCentre"))), "right ring stays at touch down beyond the limit");
        CGPoint rightKnob = rightPoint(pad, NSSelectorFromString(@"rightKnobOffset"));
        CGFloat rightRadius = ((CGFloat (*)(id, SEL))objc_msgSend)(pad, NSSelectorFromString(@"stickR"));
        check(hypot(rightKnob.x, rightKnob.y) <= rightRadius + .001 && axes[2] == 32767, "right knob and axes clamp to their limits");
        move(pad, camera, 500, 180);
        check(axes[2] == 0 && axes[3] == 0, "right origin is neutral after an over-limit drag");

        CGPoint a = ((CGPoint (*)(id, SEL, int))objc_msgSend)(pad, NSSelectorFromString(@"facePos:"), 0);
        TestTouch *attack = finger(a.x, a.y); begin(pad, attack);
        check((buttons & 1) != 0 && axes[0] < 0, "button and movement retain independent ownership");
        move(pad, camera, 512, 172); poll(YES);
        check((buttons & 1) != 0 && axes[0] < 0 && axes[2] > 0, "three simultaneous controls");
        end(pad, camera); check(axes[2] == 0 && axes[0] < 0 && (buttons & 1), "camera release preserves other fingers");
        end(pad, attack); check(buttons == 0 && axes[0] < 0, "button release preserves movement");
        usleep(50000); // a 20 FPS read interval includes time before touch-down
        camera = finger(500, 180); begin(pad, camera);
        camera.point = CGPointMake(506, 180);
        end(pad, camera); poll(YES);
        check(axes[2] == 0 && axes[3] == 0, "release before a game read discards terminal right-stick displacement");
        poll(YES); check(axes[2] == 0 && axes[3] == 0, "released swipe has no second camera sample");
        CGPoint centre = ((CGPoint (*)(id, SEL))objc_msgSend)(pad, NSSelectorFromString(@"faceCenter"));
        camera = finger(centre.x, centre.y); begin(pad, camera);
        move(pad, camera, centre.x - 6, centre.y); poll(YES);
        check(axes[2] < 0 && buttons == 0, "empty gap between face buttons starts a right stick");
        [pad touchesCancelled:[NSSet setWithObject:camera] withEvent:nil]; poll(YES);
        check(axes[2] == 0 && axes[3] == 0, "cancelled gesture discards pending camera motion");
        [pad touchesCancelled:[NSSet setWithObject:left] withEvent:nil];
        check(axes[0] == 0 && axes[1] == 0, "cancellation resets movement");

        left = finger(130, 260); begin(pad, left);
        CGPoint (*point)(id, SEL) = (void *)objc_msgSend;
        CGPoint origin = point(pad, NSSelectorFromString(@"stickCentre"));
        move(pad, left, 360, 260);
        check(CGPointEqualToPoint(origin, point(pad, NSSelectorFromString(@"stickCentre"))), "drag outside the limit keeps the ring fixed");
        CGFloat radius = ((CGFloat (*)(id, SEL))objc_msgSend)(pad, NSSelectorFromString(@"stickR"));
        CGPoint knob = point(pad, NSSelectorFromString(@"knobOffset"));
        check(hypot(knob.x, knob.y) <= radius + .001 && axes[0] == 32767, "knob and analog output saturate at the limit");
        move(pad, left, 130, 260); check(axes[0] == 0, "return to the original touch point is neutral");
        end(pad, left);
        left = finger(150, 280); begin(pad, left);
        check(CGPointEqualToPoint(point(pad, NSSelectorFromString(@"stickCentre")), CGPointMake(150, 280)), "new contact chooses a new origin");
        end(pad, left);

        left = finger(130, 260); begin(pad, left); move(pad, left, 90, 260);
        parent.bounds = CGRectMake(0, 0, 900, 402);
        [parent setNeedsLayout]; [parent layoutIfNeeded]; [pad layoutIfNeeded];
        check(axes[0] == 0 && CGRectEqualToRect(pad.bounds, parent.bounds), "resize releases controls and updates geometry");
        left = finger(130, 260); begin(pad, left); move(pad, left, 90, 260);
        [parent reset];
        dispatch_async(dispatch_get_main_queue(), ^{
            check(parent.subviews.firstObject == pad, "container survives queued reset");
            check(oldReset == 0 && axes[0] == 0 && buttons == 0, "original host reset reaches replacement overlay");
            NSDictionary *result = @{@"status": @"passed", @"checks": @(checks)};
            NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];
            NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
            check([data writeToURL:[documents URLByAppendingPathComponent:@"touch-result.json"] atomically:YES], "result written");
            NSLog(@"[touch-test] %u UIKit integration checks passed", checks);
            exit(0);
        });
    });
}

@interface TestDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation TestDelegate
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)app; (void)options;
    dispatch_async(dispatch_get_main_queue(), ^{ runTests(); }); return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(TestDelegate.class)); }
}

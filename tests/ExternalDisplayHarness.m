// Local UIKit lifecycle checks. GitHub only compiles this file; it does not run it.
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import "DmExternalDisplay.h"
#include <stdlib.h>
#include <math.h>

@interface ExternalTestRenderer : UIView
@end
@implementation ExternalTestRenderer
+ (Class)layerClass { return CAMetalLayer.class; }
- (void)layoutSubviews {
    [super layoutSubviews];
    ((CAMetalLayer *)self.layer).drawableSize = CGSizeMake(self.bounds.size.width * self.layer.contentsScale,
                                                         self.bounds.size.height * self.layer.contentsScale);
}
@end

@interface ExternalTestPad : UIView
@property (nonatomic) unsigned resets;
- (void)reset;
@end
@implementation ExternalTestPad
- (void)reset { self.resets++; }
@end
@interface ExternalTestRoot : UIViewController
@property (nonatomic, strong) UIView *game;
@property (nonatomic, strong) ExternalTestPad *pad;
@end
@implementation ExternalTestRoot
@end

static unsigned checks;
static void check(BOOL condition, const char *name) {
    checks++;
    if (!condition) { NSLog(@"[external-test] FAIL: %s", name); exit(1); }
}

void dm_run_external_display_lifecycle_tests(void) {
    NSCAssert(NSThread.isMainThread, @"Run UIKit checks on the main thread");
    ExternalTestRoot *phone = [ExternalTestRoot new];
    phone.view = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 874, 402)];
    UIView *renderer = [[ExternalTestRenderer alloc] initWithFrame:CGRectMake(79, 0, 714, 402)];
    renderer.layer.contentsScale = 3;
    phone.game = renderer; [phone.view addSubview:renderer];
    phone.pad = [ExternalTestPad new]; [phone.view addSubview:phone.pad];
    CALayer *identity = renderer.layer;
    CGRect originalFrame = renderer.frame;
    UIWindow *tv = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 3840, 2160)];
    tv.rootViewController = [UIViewController new];
    [tv.rootViewController loadViewIfNeeded]; tv.rootViewController.view.frame = tv.bounds;
    DmExternalDisplaySession *session = [[DmExternalDisplaySession alloc] initWithRoot:phone renderView:renderer];
    check([session attachToWindow:tv nativeScale:1], "renderer attaches to TV");
    check(renderer.superview == tv.rootViewController.view, "renderer belongs to the TV container");
    check(renderer.layer == identity && phone.game == renderer, "renderer and Metal layer identities survive");
    check(phone.pad.superview == phone.view, "controls stay on the phone");
    check(!tv.isKeyWindow, "TV does not take keyboard ownership");
    check(CGSizeEqualToSize(((CAMetalLayer *)renderer.layer).drawableSize, CGSizeMake(1920, 1080)), "4K output uses the 1080p drawable budget");
    check(fabs(renderer.frame.size.width / renderer.frame.size.height - 16.0 / 9.0) < .000001, "picture remains 16:9");
    tv.rootViewController.view.bounds = CGRectMake(0, 0, 1024, 768);
    [session layoutWithNativeScale:1];
    check(CGRectEqualToRect(renderer.frame, CGRectMake(0, 96, 1024, 576)), "non-16:9 monitor is letterboxed");
    [session detach];
    check(renderer.superview == phone.view && phone.view.subviews.firstObject == renderer, "unplug restores renderer below controls");
    check(CGRectEqualToRect(renderer.frame, originalFrame), "phone frame is restored");
    check(renderer.layer == identity && renderer.layer.contentsScale == 3, "native phone scale is restored");
    check(phone.pad.resets == 2 && !session.isActive, "route changes release controls");
    [session detach];
    check(phone.pad.resets == 2, "duplicate disconnect is harmless");
    UIWindow *empty = [[UIWindow alloc] initWithFrame:CGRectZero];
    empty.rootViewController = [UIViewController new];
    [empty.rootViewController loadViewIfNeeded]; empty.rootViewController.view.frame = CGRectZero;
    check(![session attachToWindow:empty nativeScale:1] && renderer.superview == phone.view, "zero-size display cannot steal renderer");
    NSLog(@"[external-test] %u lifecycle checks passed", checks);
}

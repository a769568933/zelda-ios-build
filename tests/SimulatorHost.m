#import <UIKit/UIKit.h>
#import <objc/message.h>
#include <stdint.h>
#include <stdlib.h>
#include "front.h"

static uint64_t buttons;
static int32_t axes[4];
static unsigned oldInit, oldLayout, oldReset, checks;
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

    TestTouch *left = finger(6, 250); begin(pad, left);
    check(axes[0] == 0 && axes[1] == 0, "touch down is neutral");
    move(pad, left, 0, 250);
    check(axes[0] == -32767, "full left fits on screen at the extreme edge");
    end(pad, left); check(axes[0] == 0, "left release resets input");

    left = finger(130, 260); begin(pad, left); move(pad, left, 90, 260);
    check(axes[0] < 0, "floating movement away from the idle ring");
    TestTouch *camera = finger(500, 180); begin(pad, camera);
    check(axes[2] == 0 && axes[3] == 0, "camera touch down is neutral");
    move(pad, camera, 508, 172); [pad cameraFrame:nil];
    check(axes[2] > 0 && axes[3] > 0 && axes[0] < 0, "move and camera run together");
    [pad cameraFrame:nil]; check(axes[2] == 0 && axes[3] == 0, "stationary camera finger stops");

    CGPoint a = ((CGPoint (*)(id, SEL, int))objc_msgSend)(pad, NSSelectorFromString(@"facePos:"), 0);
    TestTouch *attack = finger(a.x, a.y); begin(pad, attack);
    check((buttons & 1) != 0 && axes[0] < 0, "button and movement retain independent ownership");
    move(pad, camera, 512, 172); [pad cameraFrame:nil];
    check((buttons & 1) != 0 && axes[0] < 0 && axes[2] > 0, "three simultaneous controls");
    end(pad, camera); check(axes[2] == 0 && axes[0] < 0 && (buttons & 1), "camera release preserves other fingers");
    end(pad, attack); check(buttons == 0 && axes[0] < 0, "button release preserves movement");
    [pad touchesCancelled:[NSSet setWithObject:left] withEvent:nil];
    check(axes[0] == 0 && axes[1] == 0, "cancellation resets movement");

    left = finger(130, 260); begin(pad, left); move(pad, left, 90, 260);
    parent.bounds = CGRectMake(0, 0, 900, 402);
    [parent setNeedsLayout]; [parent layoutIfNeeded]; [pad layoutIfNeeded];
    check(axes[0] == 0 && CGRectEqualToRect(pad.bounds, parent.bounds), "resize releases controls and updates geometry");
    left = finger(130, 260); begin(pad, left); move(pad, left, 90, 260);
    [parent reset];
    dispatch_async(dispatch_get_main_queue(), ^{
        check(oldReset == 0 && axes[0] == 0 && buttons == 0, "original host reset reaches replacement overlay");
        NSDictionary *result = @{@"status": @"passed", @"checks": @(checks)};
        NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];
        NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        check([data writeToURL:[documents URLByAppendingPathComponent:@"touch-result.json"] atomically:YES], "result written");
        NSLog(@"[touch-test] %u UIKit integration checks passed", checks);
        exit(0);
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

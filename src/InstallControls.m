#import <UIKit/UIKit.h>
#import <objc/runtime.h>

// The original executable exports this class and the two host input functions.
// Keep the original object as a container. Its old initializer, layout and reset
// are exchanged before main; the original host and shader code stay intact.
@interface DmGamepad : UIView
- (void)reset;
@end

UIView *dm_phone_gamepad_view(CGRect frame);
void dm_phone_gamepad_reset(void);
static char overlayKey;

@interface DmGamepad (PhoneControls)
- (instancetype)phone_initWithFrame:(CGRect)frame __attribute__((objc_method_family(init)));
- (void)phone_layoutSubviews;
- (void)phone_reset;
@end

@implementation DmGamepad (PhoneControls)
+ (void)load {
    Class cls = self;
    SEL original[] = {@selector(initWithFrame:), @selector(layoutSubviews), @selector(reset)};
    SEL replacement[] = {@selector(phone_initWithFrame:), @selector(phone_layoutSubviews), @selector(phone_reset)};
    Method old[3], next[3];
    for (int i = 0; i < 3; i++) {
        old[i] = class_getInstanceMethod(cls, original[i]);
        next[i] = class_getInstanceMethod(cls, replacement[i]);
        if (!old[i] || !next[i]) { NSLog(@"[phone-controls] Required method missing; keeping the original controls"); return; }
    }
    for (int i = 0; i < 3; i++) method_exchangeImplementations(old[i], next[i]);
    NSLog(@"[phone-controls] Dual locked-origin sticks installed; release returns to neutral");
}
- (instancetype)phone_initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        self.backgroundColor = UIColor.clearColor;
        self.opaque = NO; self.multipleTouchEnabled = YES;
        UIView *pad = dm_phone_gamepad_view(self.bounds);
        pad.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
        objc_setAssociatedObject(self, &overlayKey, pad, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        [self addSubview:pad];
    }
    return self;
}
- (void)phone_layoutSubviews {
    [super layoutSubviews];
    UIView *pad = objc_getAssociatedObject(self, &overlayKey);
    pad.frame = self.bounds;
}
- (void)phone_reset {
    dm_phone_gamepad_reset();
}
@end

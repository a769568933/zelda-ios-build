#import <UIKit/UIKit.h>

// Reparent the existing renderer; never replace the host's CAMetalLayer.
@interface DmExternalDisplaySession : NSObject
@property (nonatomic, strong, readonly) UIView *renderView;
@property (nonatomic, strong, readonly) UIViewController *phoneRoot;
@property (nonatomic, strong, readonly) UIWindow *outputWindow;
@property (nonatomic, readonly, getter=isActive) BOOL active;
- (instancetype)initWithRoot:(UIViewController *)root renderView:(UIView *)view;
- (BOOL)attachToWindow:(UIWindow *)window nativeScale:(CGFloat)scale;
- (void)layoutWithNativeScale:(CGFloat)scale;
- (void)constrainDrawable;
- (void)detach;
@end

void dm_external_display_install(void);

// Independent noninteractive TV scene for the original App/DmRootVC host.
// No guest addresses or game assets are used. The phone keeps its controls.
#import "DmExternalDisplay.h"
#import <QuartzCore/CAMetalLayer.h>
#import <objc/message.h>
#import <objc/runtime.h>
#include <stdlib.h>
#include "DmExternalGeometry.h"

static NSString *const DMConfiguration = @"DMExternalTV";
static char DMRegistrationKey;

static id objectGetter(id object, NSString *name) {
    SEL selector = NSSelectorFromString(name);
    return [object respondsToSelector:selector] ? ((id (*)(id, SEL))objc_msgSend)(object, selector) : nil;
}
static void resetPad(UIViewController *root) {
    id pad = objectGetter(root, @"pad");
    SEL reset = NSSelectorFromString(@"reset");
    if ([pad respondsToSelector:reset]) ((void (*)(id, SEL))objc_msgSend)(pad, reset);
}

@implementation DmExternalDisplaySession {
    __weak UIView *_savedParent;
    NSUInteger _savedIndex;
    CGRect _savedFrame;
    UIViewAutoresizing _savedAutoresizing;
    CGFloat _savedScale;
    dm_tv_plan _plan;
}
- (instancetype)initWithRoot:(UIViewController *)root renderView:(UIView *)view {
    if ((self = [super init])) {
        _phoneRoot = root; _renderView = view;
        _savedParent = view.superview;
        _savedIndex = [view.superview.subviews indexOfObjectIdenticalTo:view];
        _savedFrame = view.frame; _savedAutoresizing = view.autoresizingMask;
        _savedScale = view.layer.contentsScale;
    }
    return self;
}
- (BOOL)isActive {
    return _outputWindow && _renderView.superview == _outputWindow.rootViewController.view;
}
- (BOOL)attachToWindow:(UIWindow *)window nativeScale:(CGFloat)scale {
    if (!NSThread.isMainThread || !window.rootViewController || !_savedParent ||
        ![_renderView.layer isKindOfClass:CAMetalLayer.class]) return NO;
    [window.rootViewController loadViewIfNeeded];
    CGRect b = window.rootViewController.view.bounds;
    dm_tv_plan next = dm_tv_make_plan((dm_tv_rect){b.origin.x, b.origin.y, b.size.width, b.size.height}, scale);
    if (!next.valid) return NO; // A zero-size scene must not steal the phone renderer.
    _outputWindow = window; _plan = next;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    [_outputWindow.rootViewController.view addSubview:_renderView];
    _renderView.autoresizingMask = UIViewAutoresizingNone;
    [self layoutWithNativeScale:scale];
    [CATransaction commit];
    resetPad(_phoneRoot);
    return self.isActive;
}
- (void)layoutWithNativeScale:(CGFloat)scale {
    if (!self.isActive) return;
    CGRect b = _outputWindow.rootViewController.view.bounds;
    dm_tv_plan next = dm_tv_make_plan((dm_tv_rect){b.origin.x, b.origin.y, b.size.width, b.size.height}, scale);
    if (!next.valid) return;
    _plan = next;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    _renderView.frame = CGRectMake(next.frame.x, next.frame.y, next.frame.w, next.frame.h);
    [self constrainDrawable];
    [_renderView setNeedsLayout];
    [_renderView layoutIfNeeded];
    [self constrainDrawable];
    [CATransaction commit];
}
- (void)constrainDrawable {
    if (!self.isActive || !_plan.valid) return;
    CAMetalLayer *layer = (CAMetalLayer *)_renderView.layer;
    layer.contentsScale = _plan.contents_scale;
    CGSize size = CGSizeMake(_plan.pixel_width, _plan.pixel_height);
    if (!CGSizeEqualToSize(layer.drawableSize, size)) layer.drawableSize = size;
}
- (void)detach {
    if (!_outputWindow) return;
    UIView *parent = _savedParent;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    [_renderView removeFromSuperview];
    _outputWindow = nil; _plan = (dm_tv_plan){0};
    if (parent) {
        NSUInteger index = MIN(_savedIndex, parent.subviews.count);
        [parent insertSubview:_renderView atIndex:index];
        _renderView.autoresizingMask = _savedAutoresizing;
        _renderView.frame = _savedFrame;
        UIScreen *screen = parent.window.windowScene.screen;
        CGFloat scale = screen.nativeScale;
        _renderView.layer.contentsScale = scale > 0 ? scale : _savedScale;
        [parent setNeedsLayout]; [parent layoutIfNeeded];
        [_renderView setNeedsLayout]; [_renderView layoutIfNeeded];
    }
    [CATransaction commit];
    resetPad(_phoneRoot);
}
@end

static __weak UIViewController *s_phoneRoot;
static UIWindow *s_tvWindow;
static DmExternalDisplaySession *s_session;
static BOOL s_routing;
static id s_activeObserver;
static void routeDisplay(void);

@interface DmExternalTVController : UIViewController
@end
@implementation DmExternalTVController
- (void)viewDidLoad { [super viewDidLoad]; self.view.backgroundColor = UIColor.blackColor; }
- (void)viewDidLayoutSubviews { [super viewDidLayoutSubviews]; routeDisplay(); }
- (BOOL)prefersStatusBarHidden { return YES; }
@end

@interface DmExternalSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property (nonatomic, strong) UIWindow *window;
@end
@implementation DmExternalSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.frame = ((UIWindowScene *)scene).coordinateSpace.bounds;
    self.window.rootViewController = [DmExternalTVController new];
    [self.window.rootViewController loadViewIfNeeded];
    self.window.rootViewController.view.frame = self.window.bounds;
    self.window.userInteractionEnabled = NO;
    // Show only once the existing renderer has moved. Never make this window key.
    self.window.hidden = YES;
    s_tvWindow = self.window;
    routeDisplay();
}
- (void)sceneDidBecomeActive:(UIScene *)scene { (void)scene; routeDisplay(); }
- (void)sceneDidDisconnect:(UIScene *)scene {
    (void)scene;
    if (s_tvWindow == self.window) {
        DmExternalDisplaySession *previous = s_session;
        s_session = nil; s_tvWindow = nil;
        [previous detach];
        NSLog(@"[external-display] TV disconnected; renderer restored to the phone");
    }
    self.window.hidden = YES; self.window = nil;
}
@end

static void routeDisplay(void) {
    if (!NSThread.isMainThread || s_routing || !s_phoneRoot || !s_tvWindow) return;
    s_routing = YES;
    @try {
        id view = objectGetter(s_phoneRoot, @"game");
        if (![view isKindOfClass:UIView.class] || ![[(UIView *)view layer] isKindOfClass:CAMetalLayer.class]) return;
        if (s_session && (s_session.renderView != view || s_session.phoneRoot != s_phoneRoot ||
                          s_session.outputWindow != s_tvWindow)) {
            DmExternalDisplaySession *previous = s_session; s_session = nil;
            [previous detach];
        }
        CGFloat scale = s_tvWindow.windowScene.screen.nativeScale;
        if (scale <= 0) return;
        if (!s_session) {
            DmExternalDisplaySession *next = [[DmExternalDisplaySession alloc] initWithRoot:s_phoneRoot renderView:view];
            s_session = next; // Layout hooks can now constrain the existing layer.
            if (![next attachToWindow:s_tvWindow nativeScale:scale]) { s_session = nil; return; }
            CGSize pixels = ((CAMetalLayer *)((UIView *)view).layer).drawableSize;
            NSLog(@"[external-display] Independent TV active: %.0fx%.0f pixels, 16:9; phone controls retained",
                  pixels.width, pixels.height);
        } else [s_session layoutWithNativeScale:scale];
        s_tvWindow.hidden = NO;
    } @finally { s_routing = NO; }
}

static void registerAccessory(UIViewController *root) {
    if (objc_getAssociatedObject(root, &DMRegistrationKey)) return;
    // Runtime dispatch is deliberate: compiling with an iOS 26 SDK must not
    // remove the iOS 27 scene-accessory registration from an older app.
    Class accessory = NSClassFromString(@"UISceneAccessory");
    SEL create = NSSelectorFromString(@"externalNonInteractiveSceneAccessoryWithConfiguration:");
    SEL registerSelector = NSSelectorFromString(@"registerSceneAccessory:");
    if (![accessory respondsToSelector:create] || ![root respondsToSelector:registerSelector]) {
        if (@available(iOS 27.0, *))
            NSLog(@"[external-display] iOS 27 scene-accessory API unavailable; phone renderer retained");
        return;
    }
    UISceneConfiguration *configuration = [[UISceneConfiguration alloc]
        initWithName:DMConfiguration sessionRole:UIWindowSceneSessionRoleExternalDisplayNonInteractive];
    configuration.delegateClass = DmExternalSceneDelegate.class;
    id declaration = ((id (*)(id, SEL, id))objc_msgSend)(accessory, create, configuration);
    id registration = declaration ? ((id (*)(id, SEL, id))objc_msgSend)(root, registerSelector, declaration) : nil;
    if (registration) {
        objc_setAssociatedObject(root, &DMRegistrationKey, registration, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        NSLog(@"[external-display] Noninteractive TV scene accessory registered");
    }
}

static void (*s_rootAppear)(id, SEL, BOOL);
static void (*s_rootLayout)(id, SEL);
static void (*s_gameLayout)(id, SEL);
static UISceneConfiguration *(*s_configuration)(id, SEL, UIApplication *, UISceneSession *, UISceneConnectionOptions *);

static void rootAppear(id root, SEL selector, BOOL animated) {
    s_rootAppear(root, selector, animated);
    BOOL changedRoot = s_phoneRoot && s_phoneRoot != root;
    s_phoneRoot = root;
    if (changedRoot && s_session) {
        DmExternalDisplaySession *previous = s_session; s_session = nil;
        [previous detach]; s_tvWindow.hidden = YES;
    }
    registerAccessory(root);
    routeDisplay();
}
static void rootLayout(id root, SEL selector) {
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    s_rootLayout(root, selector);
    // The old root unconditionally gives game.frame the phone's rectangle.
    // Correct the final geometry before this UI transaction is committed.
    if (s_phoneRoot == root) routeDisplay();
    [CATransaction commit];
}
static void gameLayout(id view, SEL selector) {
    s_gameLayout(view, selector);
    if (s_session.renderView == view) [s_session constrainDrawable];
}
static UISceneConfiguration *configuration(id appDelegate, SEL selector, UIApplication *app,
                                           UISceneSession *session, UISceneConnectionOptions *options) {
    if ([session.role isEqualToString:UIWindowSceneSessionRoleExternalDisplayNonInteractive] ||
        [session.role isEqualToString:UIWindowSceneSessionRoleExternalDisplay]) {
        UISceneConfiguration *result = [[UISceneConfiguration alloc] initWithName:DMConfiguration sessionRole:session.role];
        result.delegateClass = DmExternalSceneDelegate.class;
        return result;
    }
    return s_configuration(appDelegate, selector, app, session, options);
}

static Method ownedMethod(Class cls, SEL selector) {
    unsigned count = 0;
    Method *methods = class_copyMethodList(cls, &count);
    Method found = NULL;
    for (unsigned i = 0; i < count; i++)
        if (sel_isEqual(method_getName(methods[i]), selector)) { found = methods[i]; break; }
    free(methods);
    return found;
}

void dm_external_display_install(void) {
    if (![[NSBundle.mainBundle objectForInfoDictionaryKey:@"DMExternalDisplayEnabled"] boolValue]) return;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        Class root = NSClassFromString(@"DmRootVC"), game = NSClassFromString(@"DmGameView"), app = NSClassFromString(@"App");
        SEL appear = @selector(viewDidAppear:), layout = @selector(viewDidLayoutSubviews), gameLayoutSelector = @selector(layoutSubviews);
        SEL configure = @selector(application:configurationForConnectingSceneSession:options:);
        // Never replace an inherited UIKit method on UIView/UIViewController.
        Method a = ownedMethod(root, appear), b = ownedMethod(root, layout);
        Method c = ownedMethod(game, gameLayoutSelector), d = ownedMethod(app, configure);
        if (!a || !b || !c || !d || !class_getInstanceMethod(root, NSSelectorFromString(@"game"))) {
            NSLog(@"[external-display] Compatible host interfaces missing; independent output disabled");
            return;
        }
        s_rootAppear = (void *)method_setImplementation(a, (IMP)rootAppear);
        s_rootLayout = (void *)method_setImplementation(b, (IMP)rootLayout);
        s_gameLayout = (void *)method_setImplementation(c, (IMP)gameLayout);
        s_configuration = (void *)method_setImplementation(d, (IMP)configuration);
        s_activeObserver = [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationDidBecomeActiveNotification
            object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
                (void)note; if (s_phoneRoot) registerAccessory(s_phoneRoot); routeDisplay();
            }];
        NSLog(@"[external-display] Independent 16:9 TV adapter installed (1080p drawable limit)");
    });
}

@interface DmExternalBootstrap : NSObject
@end
@implementation DmExternalBootstrap
+ (void)load { dm_external_display_install(); }
@end

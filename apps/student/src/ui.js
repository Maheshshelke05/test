import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  Animated,
  Easing,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { colors, radius, shadow, space, STATUS, type } from './theme';

let reduceMotion = false;
AccessibilityInfo.isReduceMotionEnabled?.().then((v) => (reduceMotion = !!v)).catch(() => {});
export const motionOK = () => !reduceMotion;
// The native animation driver exists on devices only; on web it just logs a warning.
export const nativeDriver = Platform.OS !== 'web';

export function PressScale({ onPress, disabled, style, children, accessibilityLabel, accessibilityRole = 'button', hitSlop, testID }) {
  const scale = useRef(new Animated.Value(1)).current;
  const to = (v) =>
    motionOK() && Animated.spring(scale, { toValue: v, useNativeDriver: nativeDriver, speed: 40, bounciness: 6 }).start();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      onPressIn={() => to(0.97)}
      onPressOut={() => to(1)}
      accessibilityRole={accessibilityRole}
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: !!disabled }}
      hitSlop={hitSlop}
      testID={testID}
    >
      <Animated.View style={[style, { transform: [{ scale }] }, disabled && { opacity: 0.5 }]}>{children}</Animated.View>
    </Pressable>
  );
}

export function Btn({ title, onPress, variant = 'primary', disabled, loading, small, style, icon, accessibilityLabel }) {
  const v = {
    primary: { bg: colors.green, fg: '#fff', border: colors.green },
    yellow: { bg: colors.yellow, fg: colors.text, border: colors.yellow },
    secondary: { bg: colors.surface, fg: colors.green, border: colors.green },
    ghost: { bg: 'transparent', fg: colors.green, border: 'transparent' },
    danger: { bg: colors.surface, fg: colors.red, border: colors.red },
  }[variant];
  return (
    <PressScale
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityLabel={accessibilityLabel || title}
      style={[
        s.btn,
        small && s.btnSmall,
        { backgroundColor: v.bg, borderColor: v.border },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={v.fg} />
      ) : (
        <Text style={[s.btnText, small && { fontSize: 13 }, { color: v.fg }]}>
          {icon ? `${icon}  ` : ''}
          {title}
        </Text>
      )}
    </PressScale>
  );
}

export function Card({ children, style, onPress, accessibilityLabel, testID }) {
  if (onPress)
    return (
      <PressScale onPress={onPress} style={[s.card, style]} accessibilityLabel={accessibilityLabel} testID={testID}>
        {children}
      </PressScale>
    );
  return <View style={[s.card, style]} testID={testID}>{children}</View>;
}

export function VegMark({ veg, size = 14 }) {
  const c = veg ? colors.veg : colors.nonveg;
  return (
    <View
      accessibilityLabel={veg ? 'Vegetarian' : 'Non-vegetarian'}
      style={{ width: size, height: size, borderWidth: 1.5, borderColor: c, borderRadius: 3, alignItems: 'center', justifyContent: 'center' }}
    >
      <View style={{ width: size / 2.2, height: size / 2.2, borderRadius: size, backgroundColor: c }} />
    </View>
  );
}

export function Chip({ label, active, onPress, style }) {
  return (
    <PressScale
      onPress={onPress}
      accessibilityLabel={label}
      style={[s.chip, active && { backgroundColor: colors.greenSoft, borderColor: colors.green }, style]}
    >
      <Text style={[s.chipText, active && { color: colors.green }]}>{label}</Text>
    </PressScale>
  );
}

export function Stepper({ qty, onInc, onDec, small, max = 50 }) {
  const pop = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (!motionOK()) return;
    pop.setValue(0.8);
    Animated.spring(pop, { toValue: 1, useNativeDriver: nativeDriver, speed: 30, bounciness: 12 }).start();
  }, [qty]);
  return (
    <View style={[s.stepper, small && { height: 32 }]}>
      <Pressable accessibilityRole="button" onPress={onDec} style={s.stepBtn} accessibilityLabel="Decrease quantity" hitSlop={8}>
        <Text style={s.stepText}>−</Text>
      </Pressable>
      <Animated.Text style={[s.stepText, { minWidth: 22, textAlign: 'center', transform: [{ scale: pop }] }]} accessibilityLabel={`Quantity ${qty}`}>
        {qty}
      </Animated.Text>
      <Pressable accessibilityRole="button" onPress={onInc} disabled={qty >= max} style={s.stepBtn} accessibilityLabel="Increase quantity" hitSlop={8}>
        <Text style={[s.stepText, qty >= max && { opacity: 0.4 }]}>+</Text>
      </Pressable>
    </View>
  );
}

export function AddButton({ qty, onAdd, onInc, onDec, disabled, hasOptions }) {
  if (disabled) {
    return (
      <View style={[s.addBtn, { borderColor: colors.border, backgroundColor: '#F1F2EF' }]}>
        <Text style={[s.addText, { color: colors.faint }]}>SOLD OUT</Text>
      </View>
    );
  }
  if (qty > 0) return <Stepper qty={qty} onInc={onInc} onDec={onDec} small />;
  return (
    <View>
      <PressScale onPress={onAdd} style={s.addBtn} accessibilityLabel="Add to cart">
        <Text style={s.addText}>ADD</Text>
      </PressScale>
      {hasOptions ? <Text style={s.customisable}>customisable</Text> : null}
    </View>
  );
}

export function Skeleton({ height = 16, width = '100%', style, r = radius.sm }) {
  const v = useRef(new Animated.Value(0.4)).current;
  useEffect(() => {
    if (!motionOK()) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: 700, useNativeDriver: nativeDriver, easing: Easing.inOut(Easing.quad) }),
        Animated.timing(v, { toValue: 0.4, duration: 700, useNativeDriver: nativeDriver, easing: Easing.inOut(Easing.quad) }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, []);
  return <Animated.View style={[{ height, width, borderRadius: r, backgroundColor: '#E5E8E3', opacity: v }, style]} />;
}

export function ListSkeleton({ rows = 4 }) {
  return (
    <View style={{ gap: 12, padding: space(2) }} accessibilityLabel="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <View key={i} style={[s.card, { flexDirection: 'row', gap: 12 }]}>
          <Skeleton width={64} height={64} r={radius.md} />
          <View style={{ flex: 1, gap: 8 }}>
            <Skeleton width="70%" />
            <Skeleton width="40%" height={12} />
            <Skeleton width="30%" height={12} />
          </View>
        </View>
      ))}
    </View>
  );
}

export function Empty({ emoji = '🍽️', title, subtitle, action, onAction }) {
  return (
    <View style={s.empty}>
      <Text style={{ fontSize: 48 }}>{emoji}</Text>
      <Text style={[type.h3, { marginTop: 12, textAlign: 'center' }]}>{title}</Text>
      {subtitle ? <Text style={[type.small, { textAlign: 'center', marginTop: 4 }]}>{subtitle}</Text> : null}
      {action ? <Btn title={action} onPress={onAction} variant="secondary" small style={{ marginTop: 16 }} /> : null}
    </View>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <Empty
      emoji={error?.code === 'NETWORK' ? '📡' : '😕'}
      title={error?.code === 'NETWORK' ? "You're offline" : 'Something went wrong'}
      subtitle={error?.message}
      action="Try again"
      onAction={onRetry}
    />
  );
}

export function StatusPill({ status, large }) {
  const st = STATUS[status] || { label: status, color: colors.muted, bg: '#eee', icon: '' };
  return (
    <View style={[s.pill, { backgroundColor: st.bg }, large && { paddingHorizontal: 14, paddingVertical: 6 }]}>
      <Text style={{ color: st.color, fontWeight: '700', fontSize: large ? 14 : 12 }}>
        {st.icon} {st.label}
      </Text>
    </View>
  );
}

export function Field({ label, error, style, inputStyle, ...props }) {
  const [focus, setFocus] = useState(false);
  return (
    <View style={[{ marginBottom: 14 }, style]}>
      {label ? <Text style={[type.small, { fontWeight: '600', marginBottom: 6, color: colors.text }]}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.faint}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        accessibilityLabel={label || props.placeholder}
        style={[s.input, focus && { borderColor: colors.green }, error && { borderColor: colors.red }, inputStyle]}
        {...props}
      />
      {error ? <Text style={[type.small, { color: colors.red, marginTop: 4 }]}>{error}</Text> : null}
    </View>
  );
}

export function Sheet({ visible, onClose, children, title }) {
  const y = useRef(new Animated.Value(400)).current;
  useEffect(() => {
    if (visible) {
      y.setValue(motionOK() ? 400 : 0);
      Animated.spring(y, { toValue: 0, useNativeDriver: nativeDriver, speed: 18, bounciness: 4 }).start();
    }
  }, [visible]);
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable accessibilityRole="button" style={s.overlay} onPress={onClose} accessibilityLabel="Close" />
      <Animated.View style={[s.sheet, { transform: [{ translateY: y }] }]}>
        <View style={s.grabber} />
        {title ? <Text style={[type.h2, { marginBottom: 12 }]}>{title}</Text> : null}
        {children}
      </Animated.View>
    </Modal>
  );
}

export function TopBar({ title, subtitle, onBack, right }) {
  return (
    <View style={s.topbar}>
      {onBack ? (
        <Pressable onPress={onBack} style={s.back} accessibilityLabel="Go back" accessibilityRole="button" hitSlop={10}>
          <Text style={{ fontSize: 22, color: colors.text }}>←</Text>
        </Pressable>
      ) : null}
      <View style={{ flex: 1 }}>
        <Text style={type.h3} numberOfLines={1}>{title}</Text>
        {subtitle ? <Text style={type.small} numberOfLines={1}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export function Scroll({ children, refreshing, onRefresh, contentStyle, ...rest }) {
  return (
    <ScrollView
      contentContainerStyle={[{ paddingBottom: 120 }, contentStyle]}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={colors.green} /> : undefined}
      keyboardShouldPersistTaps="handled"
      {...rest}
    >
      {children}
    </ScrollView>
  );
}

export function Divider({ style }) {
  return <View style={[{ height: 1, backgroundColor: colors.border, marginVertical: 12 }, style]} />;
}

export function Row({ children, style }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center' }, style]}>{children}</View>;
}

export const s = StyleSheet.create({
  btn: {
    minHeight: 48,
    borderRadius: radius.md,
    borderWidth: 1.5,
    paddingHorizontal: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnSmall: { minHeight: 36, paddingHorizontal: 12, borderRadius: radius.sm },
  btnText: { fontSize: 15, fontWeight: '800', letterSpacing: 0.2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: space(2), ...shadow },
  chip: {
    paddingHorizontal: 14,
    height: 36,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    justifyContent: 'center',
  },
  chipText: { fontSize: 13, fontWeight: '600', color: colors.text },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.green,
    borderRadius: radius.sm,
    height: 36,
    paddingHorizontal: 4,
    minWidth: 92,
    justifyContent: 'space-between',
  },
  stepBtn: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  stepText: { color: '#fff', fontSize: 17, fontWeight: '800' },
  addBtn: {
    minWidth: 92,
    height: 36,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderColor: colors.green,
    backgroundColor: colors.greenSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addText: { color: colors.green, fontWeight: '800', fontSize: 14, letterSpacing: 0.5 },
  customisable: { fontSize: 10, color: colors.muted, textAlign: 'center', marginTop: 2 },
  empty: { alignItems: 'center', justifyContent: 'center', padding: space(5) },
  pill: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  input: {
    height: 50,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    fontSize: 16,
    backgroundColor: colors.surface,
    color: colors.text,
  },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.overlay },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '88%',
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: space(2.5),
    paddingBottom: space(4),
  },
  grabber: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: space(2),
    paddingVertical: space(1.5),
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', marginLeft: -8 },
});

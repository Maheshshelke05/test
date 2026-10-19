import { useEffect, useRef, useState } from 'react';
import { Animated, FlatList, KeyboardAvoidingView, Platform, Pressable, Text, View } from 'react-native';
import { api } from '../api';
import { useApp } from '../store';
import { colors, radius, space, type } from '../theme';
import { Btn, Card, Empty, Field, ListSkeleton, motionOK, nativeDriver, Row, Scroll, TopBar } from '../ui';

const SLIDES = [
  { emoji: '⚡', title: 'Skip the canteen queue', body: 'Order from your campus kitchens in seconds and pick up when it’s ready.' },
  { emoji: '🍜', title: 'Every kitchen, one app', body: 'Maggi, thalis, momos, juices — browse menus, prices and prep times live.' },
  { emoji: '📍', title: 'Track it to the counter', body: 'Live order updates and a one-time pickup code so your meal reaches only you.' },
];

export function Onboarding() {
  const { finishOnboarding } = useApp();
  const [i, setI] = useState(0);
  const fade = useRef(new Animated.Value(1)).current;
  const go = (n) => {
    if (!motionOK()) return setI(n);
    Animated.timing(fade, { toValue: 0, duration: 120, useNativeDriver: nativeDriver }).start(() => {
      setI(n);
      Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: nativeDriver }).start();
    });
  };
  const slide = SLIDES[i];
  return (
    <View style={{ flex: 1, backgroundColor: colors.yellow }}>
      <View style={{ paddingTop: space(6), paddingHorizontal: space(3) }}>
        <Text style={{ fontSize: 30, fontWeight: '900', color: colors.green, letterSpacing: -0.5 }}>campusbite</Text>
      </View>
      <Animated.View style={{ flex: 1, justifyContent: 'center', padding: space(3), opacity: fade }}>
        <View style={{ width: 120, height: 120, borderRadius: 60, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center', marginBottom: space(4) }}>
          <Text style={{ fontSize: 60 }}>{slide.emoji}</Text>
        </View>
        <Text style={[type.h1, { fontSize: 32, lineHeight: 38 }]}>{slide.title}</Text>
        <Text style={[type.body, { fontSize: 16, lineHeight: 24, marginTop: 12, color: '#3A3A2A' }]}>{slide.body}</Text>
      </Animated.View>
      <View style={{ padding: space(3), paddingBottom: space(5) }}>
        <Row style={{ gap: 6, marginBottom: space(3) }}>
          {SLIDES.map((_, n) => (
            <View key={n} style={{ height: 6, width: n === i ? 24 : 6, borderRadius: 3, backgroundColor: n === i ? colors.green : 'rgba(22,101,52,0.25)' }} />
          ))}
        </Row>
        <Btn title={i < SLIDES.length - 1 ? 'Next' : 'Get started'} onPress={() => (i < SLIDES.length - 1 ? go(i + 1) : finishOnboarding())} />
        {i < SLIDES.length - 1 ? <Btn title="Skip" variant="ghost" onPress={finishOnboarding} style={{ marginTop: 4 }} /> : null}
      </View>
    </View>
  );
}

export function Login() {
  const { signIn, toast } = useApp();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState('phone');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [devCode, setDevCode] = useState(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const requestOtp = async () => {
    setError(null);
    if (!/^[6-9]\d{9}$/.test(phone)) return setError('Enter a valid 10-digit mobile number');
    setBusy(true);
    try {
      const r = await api('/v1/auth/otp/request', { method: 'POST', body: { phone } });
      setDevCode(r.dev_code || null);
      setStep('otp');
      setCooldown(30);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await api('/v1/auth/otp/verify', { method: 'POST', body: { phone, code } });
      await signIn(r);
      toast('Welcome to CampusBite!', 'success');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ backgroundColor: colors.yellow, paddingTop: space(7), paddingBottom: space(4), paddingHorizontal: space(3), borderBottomLeftRadius: 28, borderBottomRightRadius: 28 }}>
        <Text style={{ fontSize: 28, fontWeight: '900', color: colors.green }}>campusbite</Text>
        <Text style={[type.body, { marginTop: 6, color: '#3A3A2A' }]}>Campus food, ready when you are.</Text>
      </View>
      <View style={{ padding: space(3) }}>
        {step === 'phone' ? (
          <>
            <Text style={type.h2}>Log in or sign up</Text>
            <Text style={[type.small, { marginTop: 4, marginBottom: space(3) }]}>We’ll send a one-time password to your mobile.</Text>
            <Field
              label="Mobile number"
              placeholder="10-digit mobile number"
              keyboardType="phone-pad"
              maxLength={10}
              value={phone}
              onChangeText={(t) => setPhone(t.replace(/\D/g, ''))}
              error={error}
              onSubmitEditing={requestOtp}
              autoFocus
            />
            <Btn title="Continue" onPress={requestOtp} loading={busy} disabled={phone.length !== 10} />
          </>
        ) : (
          <>
            <Text style={type.h2}>Enter OTP</Text>
            <Text style={[type.small, { marginTop: 4, marginBottom: space(3) }]}>
              Sent to +91 {phone}.{' '}
              <Text style={{ color: colors.green, fontWeight: '700' }} onPress={() => { setStep('phone'); setCode(''); setError(null); }}>
                Change
              </Text>
            </Text>
            {devCode ? (
              <View style={{ backgroundColor: colors.yellowSoft, padding: 10, borderRadius: radius.sm, marginBottom: 12 }}>
                <Text style={type.small}>Local test mode — your OTP is <Text style={{ fontWeight: '800', color: colors.text }}>{devCode}</Text></Text>
              </View>
            ) : null}
            <Field
              label="6-digit OTP"
              placeholder="••••••"
              keyboardType="number-pad"
              maxLength={6}
              value={code}
              onChangeText={(t) => setCode(t.replace(/\D/g, ''))}
              error={error}
              inputStyle={{ letterSpacing: 8, fontSize: 22, textAlign: 'center' }}
              onSubmitEditing={verify}
              autoFocus
            />
            <Btn title="Verify & continue" onPress={verify} loading={busy} disabled={code.length < 6} />
            <Btn
              title={cooldown ? `Resend OTP in ${cooldown}s` : 'Resend OTP'}
              variant="ghost"
              disabled={cooldown > 0}
              onPress={requestOtp}
              style={{ marginTop: 6 }}
            />
          </>
        )}
        <Text style={[type.small, { marginTop: space(3), textAlign: 'center' }]}>
          By continuing you agree to CampusBite’s terms and privacy policy. We only use your number to log you in and update you about orders.
        </Text>
      </View>
    </KeyboardAvoidingView>
  );
}

export function ProfileForm({ onDone, onBack, title = 'Tell us about you' }) {
  const { user, setUser, toast } = useApp();
  const [form, setForm] = useState({ name: user?.name || '', email: user?.email || '', roll_no: user?.roll_no || '', year: user?.year || '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (v) => setForm({ ...form, [k]: v });

  const save = async () => {
    if (form.name.trim().length < 2) return setError('Please enter your name');
    if (form.email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) return setError('Enter a valid email or leave it empty');
    setBusy(true);
    try {
      const body = { name: form.name.trim(), email: form.email.trim() || null, roll_no: form.roll_no.trim() || null, year: form.year || null };
      setUser(await api('/v1/me', { method: 'PATCH', body }));
      toast('Profile saved', 'success');
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <TopBar title={title} onBack={onBack} />
      <Scroll contentStyle={{ padding: space(3) }}>
        <Field label="Full name *" value={form.name} onChangeText={set('name')} placeholder="e.g. Aarav Patil" error={error} autoFocus />
        <Field label="College email (optional)" value={form.email} onChangeText={set('email')} placeholder="you@college.edu.in" keyboardType="email-address" autoCapitalize="none" />
        <Field label="Roll number (optional)" value={form.roll_no} onChangeText={set('roll_no')} placeholder="Roll / PRN" autoCapitalize="characters" />
        <Text style={[type.small, { fontWeight: '600', color: colors.text, marginBottom: 8 }]}>Year (optional)</Text>
        <Row style={{ gap: 8, marginBottom: space(3), flexWrap: 'wrap' }}>
          {['FY', 'SY', 'TY', 'BE', 'PG', 'Staff'].map((y) => (
            <Pressable key={y} onPress={() => set('year')(form.year === y ? '' : y)} accessibilityRole="radio" accessibilityState={{ selected: form.year === y }}
              style={{ paddingHorizontal: 16, height: 40, borderRadius: 20, justifyContent: 'center', borderWidth: 1.5, borderColor: form.year === y ? colors.green : colors.border, backgroundColor: form.year === y ? colors.greenSoft : '#fff' }}>
              <Text style={{ fontWeight: '700', color: form.year === y ? colors.green : colors.text }}>{y}</Text>
            </Pressable>
          ))}
        </Row>
        <Btn title="Save" onPress={save} loading={busy} />
      </Scroll>
    </View>
  );
}

export function CollegePicker({ onBack }) {
  const { user, setUser, cart, clearCart, confirm, toast, nav } = useApp();
  const [q, setQ] = useState('');
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [coords, setCoords] = useState(null);
  const [locating, setLocating] = useState(false);
  const canLocate = typeof navigator !== 'undefined' && !!navigator.geolocation;

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q });
        if (coords) {
          params.set('lat', coords.lat);
          params.set('lng', coords.lng);
        }
        setItems((await api(`/v1/colleges?${params}`)).items);
        setError(null);
      } catch (e) {
        setError(e);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, coords]);

  const locate = () => {
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setCoords({ lat: p.coords.latitude, lng: p.coords.longitude });
        setLocating(false);
      },
      () => {
        setLocating(false);
        toast('Location unavailable — search for your college instead');
      },
      { timeout: 8000 }
    );
  };

  const choose = async (c) => {
    if (cart.kitchen && cart.kitchen.college_id !== c.id) {
      const ok = await confirm({ title: 'Switch campus?', message: 'Your cart is from another campus and will be cleared.', confirmText: 'Switch' });
      if (!ok) return;
      clearCart();
    }
    try {
      setUser(await api('/v1/me', { method: 'PATCH', body: { college_id: c.id } }));
      toast(`Campus set to ${c.name}`, 'success');
      if (onBack) onBack();
      else nav.reset();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Choose your campus" subtitle="You’ll see kitchens from this campus" onBack={onBack} />
      <View style={{ padding: space(2), backgroundColor: colors.surface }}>
        <Field placeholder="🔍  Search college or city" value={q} onChangeText={setQ} style={{ marginBottom: canLocate ? 10 : 0 }} />
        {canLocate ? (
          <Btn title={coords ? 'Sorted by distance' : 'Use my location'} icon="📍" variant="secondary" small onPress={locate} loading={locating} disabled={!!coords} />
        ) : null}
      </View>
      {error ? (
        <Empty emoji="📡" title="Couldn’t load colleges" subtitle={error.message} />
      ) : !items ? (
        <ListSkeleton rows={3} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(c) => String(c.id)}
          contentContainerStyle={{ padding: space(2), gap: 12 }}
          ListEmptyComponent={<Empty emoji="🏫" title="No colleges found" subtitle="Try a different name or city" />}
          renderItem={({ item: c }) => (
            <Card onPress={() => choose(c)} accessibilityLabel={`Choose ${c.name}`} style={user?.college_id === c.id && { borderWidth: 2, borderColor: colors.green }}>
              <Row style={{ gap: 12 }}>
                <View style={{ width: 48, height: 48, borderRadius: 12, backgroundColor: colors.yellowSoft, alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ fontSize: 24 }}>🏫</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={type.h3}>{c.name}</Text>
                  <Text style={type.small}>{c.address}</Text>
                </View>
                {c.distance_km != null ? <Text style={[type.small, { fontWeight: '700' }]}>{c.distance_km} km</Text> : null}
              </Row>
            </Card>
          )}
        />
      )}
    </View>
  );
}

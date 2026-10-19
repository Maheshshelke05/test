import { useCallback, useEffect, useState } from 'react';
import { FlatList, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { api } from '../api';
import { useApp, useLiveRefresh } from '../store';
import { colors, radius, rupees, shadow, space, STATUS, type } from '../theme';
import { Card, Chip, Divider, Empty, ErrorState, ListSkeleton, PressScale, Row, Scroll, Skeleton, TopBar, VegMark } from '../ui';
import { ItemRow, ItemSheet } from './kitchen';

const CRAVINGS = [
  { emoji: '🍜', label: 'Maggi', q: 'maggi' },
  { emoji: '☕', label: 'Chai', q: 'chai' },
  { emoji: '🍱', label: 'Thali', q: 'thali' },
  { emoji: '🥟', label: 'Momos', q: 'momos' },
  { emoji: '🍕', label: 'Pizza', q: 'pizza' },
  { emoji: '🌯', label: 'Rolls', q: 'roll' },
  { emoji: '🥤', label: 'Shakes', q: 'shake' },
  { emoji: '🍰', label: 'Dessert', q: 'brownie' },
];

function KitchenCard({ k, onPress, wide }) {
  return (
    <Card onPress={onPress} accessibilityLabel={`${k.name}, ${k.is_open ? 'open' : 'closed'}`}
      style={[{ padding: 0, overflow: 'hidden' }, wide ? { marginBottom: 12 } : { width: 220 }]}>
      <View style={{ height: wide ? 96 : 84, backgroundColor: k.is_open ? colors.yellowSoft : '#EEF0ED', alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontSize: 44, opacity: k.is_open ? 1 : 0.5 }}>{k.emoji}</Text>
        {!k.is_open ? (
          <View style={{ position: 'absolute', top: 8, left: 8, backgroundColor: colors.text, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
            <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800' }}>CLOSED</Text>
          </View>
        ) : k.busy_mode ? (
          <View style={{ position: 'absolute', top: 8, left: 8, backgroundColor: colors.yellow, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
            <Text style={{ fontSize: 11, fontWeight: '800' }}>BUSY</Text>
          </View>
        ) : null}
        {k.rating ? (
          <View style={{ position: 'absolute', top: 8, right: 8, backgroundColor: colors.green, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
            <Text style={{ color: '#fff', fontSize: 12, fontWeight: '800' }}>★ {k.rating}</Text>
          </View>
        ) : null}
      </View>
      <View style={{ padding: 12 }}>
        <Text style={type.h3} numberOfLines={1}>{k.name}</Text>
        <Text style={type.small} numberOfLines={1}>{k.cuisine}</Text>
        <Text style={[type.small, { marginTop: 4, color: colors.text, fontWeight: '600' }]}>
          {k.is_open ? `⏱ ${k.prep_minutes} min · ${k.counter_location}` : k.closed_reason}
        </Text>
      </View>
    </Card>
  );
}

function ActiveOrderBanner({ orders, onOpen }) {
  if (!orders?.length) return null;
  const o = orders[0];
  const st = STATUS[o.status];
  return (
    <PressScale onPress={() => onOpen(o)} accessibilityLabel={`Track order ${o.order_number}`}
      style={{ marginHorizontal: space(2), marginTop: space(2), backgroundColor: o.status === 'READY' ? colors.green : colors.surface, borderRadius: radius.lg, padding: 14, ...shadow }}>
      <Row style={{ gap: 12 }}>
        <Text style={{ fontSize: 28 }}>{st.icon}</Text>
        <View style={{ flex: 1 }}>
          <Text style={[type.h3, o.status === 'READY' && { color: '#fff' }]}>{st.label}</Text>
          <Text style={[type.small, o.status === 'READY' && { color: '#E7F4EC' }]}>
            {o.order_number} · {o.kitchen.name}{orders.length > 1 ? ` · +${orders.length - 1} more` : ''}
          </Text>
        </View>
        <Text style={{ fontWeight: '800', color: o.status === 'READY' ? '#fff' : colors.green }}>{o.status === 'READY' ? 'Show code →' : 'Track →'}</Text>
      </Row>
    </PressScale>
  );
}

export function HomeScreen() {
  const { user, nav, live } = useApp();
  const [kitchens, setKitchens] = useState(null);
  const [popular, setPopular] = useState([]);
  const [active, setActive] = useState([]);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const cid = user.college_id;

  const load = useCallback(async () => {
    try {
      const [k, p, o] = await Promise.all([
        api(`/v1/colleges/${cid}/kitchens`),
        api(`/v1/colleges/${cid}/popular`),
        api('/v1/orders?active=true&size=5'),
      ]);
      setKitchens(k.items);
      setPopular(p.items);
      setActive(o.items);
      setError(null);
    } catch (e) {
      setError(e);
    }
    setRefreshing(false);
  }, [cid]);
  useEffect(() => {
    setKitchens(null);
    load();
  }, [load]);
  useLiveRefresh(load, (e) => e.type === 'order_updated');

  const openKitchens = (kitchens || []).filter((k) => k.is_open);
  const hour = new Date().getHours();
  const greet = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <Scroll refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} stickyHeaderIndices={[1]}>
        <View style={{ backgroundColor: colors.yellow, paddingTop: space(5), paddingHorizontal: space(2), paddingBottom: space(1.5) }}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Pressable accessibilityRole="button" onPress={() => nav.push('college')} accessibilityLabel="Change campus" style={{ flex: 1 }}>
              <Text style={[type.label, { color: '#5A4A00' }]}>Pickup at {live ? '· 🟢 live' : ''}</Text>
              <Text style={[type.h2, { fontSize: 18 }]} numberOfLines={1}>{user.college?.name || 'Choose campus'} ▾</Text>
            </Pressable>
            <Pressable accessibilityRole="button" onPress={() => nav.tab('profile')} accessibilityLabel="Profile"
              style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ fontWeight: '800', color: colors.green }}>{(user.name || '?')[0].toUpperCase()}</Text>
            </Pressable>
          </Row>
        </View>
        <View style={{ backgroundColor: colors.yellow, paddingHorizontal: space(2), paddingBottom: space(1.5) }}>
          <Pressable onPress={() => nav.push('search')} accessibilityRole="search" accessibilityLabel="Search for dishes"
            style={{ height: 48, borderRadius: radius.md, backgroundColor: '#fff', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, gap: 10 }}>
            <Text style={{ fontSize: 16 }}>🔍</Text>
            <Text style={{ color: colors.faint, fontSize: 15 }}>Search “cheese maggi”, “cold coffee”…</Text>
          </Pressable>
        </View>

        <ActiveOrderBanner orders={active} onOpen={(o) => nav.push('order', { orderId: o.id })} />

        <View style={{ margin: space(2), borderRadius: radius.lg, backgroundColor: colors.green, padding: space(2.5), overflow: 'hidden' }}>
          <Text style={{ color: colors.yellow, fontWeight: '800', fontSize: 12, letterSpacing: 1 }}>{greet.toUpperCase()}, {(user.name || '').split(' ')[0].toUpperCase()}</Text>
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '900', marginTop: 6, lineHeight: 28 }}>Skip the queue.{'\n'}Order ahead, pick up hot.</Text>
          <Text style={{ color: '#CDE9D6', marginTop: 6 }}>{openKitchens.length} kitchens open now on your campus</Text>
          <Text style={{ position: 'absolute', right: 12, bottom: -6, fontSize: 70, opacity: 0.9 }}>🍱</Text>
        </View>

        <Text style={[type.h3, { marginHorizontal: space(2), marginBottom: 8 }]}>What are you craving?</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: space(2), gap: 12 }}>
          {CRAVINGS.map((c) => (
            <PressScale key={c.label} onPress={() => nav.push('search', { q: c.q })} accessibilityLabel={c.label} style={{ alignItems: 'center', width: 68 }}>
              <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadow }}>
                <Text style={{ fontSize: 30 }}>{c.emoji}</Text>
              </View>
              <Text style={[type.small, { color: colors.text, fontWeight: '600', marginTop: 6 }]}>{c.label}</Text>
            </PressScale>
          ))}
        </ScrollView>

        <Row style={{ justifyContent: 'space-between', marginHorizontal: space(2), marginTop: space(3), marginBottom: 8 }}>
          <Text style={type.h3}>Kitchens on campus</Text>
          <Pressable accessibilityRole="button" onPress={() => nav.tab('kitchens')} hitSlop={8}><Text style={{ color: colors.green, fontWeight: '700' }}>See all</Text></Pressable>
        </Row>
        {error ? (
          <ErrorState error={error} onRetry={load} />
        ) : !kitchens ? (
          <ScrollView horizontal contentContainerStyle={{ paddingHorizontal: space(2), gap: 12 }}>
            {[0, 1].map((i) => <Skeleton key={i} width={220} height={160} r={radius.lg} />)}
          </ScrollView>
        ) : kitchens.length === 0 ? (
          <Empty emoji="🏗️" title="No kitchens yet" subtitle="Kitchens on this campus are still being onboarded." />
        ) : (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: space(2), gap: 12, paddingBottom: 8 }}>
            {kitchens.map((k) => <KitchenCard key={k.id} k={k} onPress={() => nav.push('kitchen', { kitchenId: k.id })} />)}
          </ScrollView>
        )}

        {popular.length ? (
          <>
            <Text style={[type.h3, { marginHorizontal: space(2), marginTop: space(3), marginBottom: 8 }]}>Popular on campus 🔥</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: space(1.5) }}>
              {popular.map((it) => {
                const k = (kitchens || []).find((x) => x.id === it.kitchen.id);
                return (
                  <View key={it.id} style={{ width: '50%', padding: 4 }}>
                    <Card onPress={() => nav.push('kitchen', { kitchenId: it.kitchen.id, openItemId: it.id })} style={{ padding: 10 }}
                      accessibilityLabel={`${it.name} from ${it.kitchen.name}, ${rupees(it.price_paise)}`}>
                      <View style={{ height: 80, borderRadius: radius.md, backgroundColor: colors.yellowSoft, alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ fontSize: 40 }}>{it.emoji}</Text>
                      </View>
                      <Row style={{ gap: 4, marginTop: 8 }}><VegMark veg={it.is_veg} size={12} /><Text style={[type.small]} numberOfLines={1}>{it.kitchen.name}</Text></Row>
                      <Text style={[type.body, { fontWeight: '700', minHeight: 40 }]} numberOfLines={2}>{it.name}</Text>
                      <Row style={{ justifyContent: 'space-between' }}>
                        <Text style={{ fontWeight: '800' }}>{rupees(it.price_paise)}</Text>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: k?.is_open === false ? colors.faint : colors.green }}>{k?.is_open === false ? 'Closed' : 'View →'}</Text>
                      </Row>
                    </Card>
                  </View>
                );
              })}
            </View>
          </>
        ) : null}
      </Scroll>
    </View>
  );
}

export function KitchensScreen() {
  const { user, nav } = useApp();
  const [q, setQ] = useState('');
  const [veg, setVeg] = useState(false);
  const [openOnly, setOpenOnly] = useState(false);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ q, veg_only: veg });
      setItems((await api(`/v1/colleges/${user.college_id}/kitchens?${params}`)).items);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [q, veg, user.college_id]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const shown = (items || []).filter((k) => !openOnly || k.is_open);
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.surface, paddingTop: space(5), paddingHorizontal: space(2), paddingBottom: space(1.5) }}>
        <Text style={type.h1}>Kitchens</Text>
        <Text style={type.small}>{user.college?.name}</Text>
        <TextInput value={q} onChangeText={setQ} placeholder="🔍  Search kitchens or cuisine" placeholderTextColor={colors.faint}
          accessibilityLabel="Search kitchens"
          style={{ height: 46, borderRadius: radius.md, backgroundColor: colors.bg, paddingHorizontal: 14, marginTop: 12, fontSize: 15, color: colors.text }} />
        <Row style={{ gap: 8, marginTop: 10 }}>
          <Chip label="🟢 Pure veg options" active={veg} onPress={() => setVeg(!veg)} />
          <Chip label="Open now" active={openOnly} onPress={() => setOpenOnly(!openOnly)} />
        </Row>
      </View>
      {error ? <ErrorState error={error} onRetry={load} /> : !items ? <ListSkeleton /> : (
        <FlatList
          data={shown}
          keyExtractor={(k) => String(k.id)}
          contentContainerStyle={{ padding: space(2), paddingBottom: 140 }}
          renderItem={({ item }) => <KitchenCard k={item} wide onPress={() => nav.push('kitchen', { kitchenId: item.id })} />}
          ListEmptyComponent={<Empty emoji="🔎" title="No kitchens match" subtitle="Try clearing filters" action="Clear filters" onAction={() => { setQ(''); setVeg(false); setOpenOnly(false); }} />}
        />
      )}
    </View>
  );
}

export function SearchScreen({ q: initial = '', kitchenId }) {
  const { user, nav } = useApp();
  const [q, setQ] = useState(initial);
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sheet, setSheet] = useState(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setRes(null);
      return;
    }
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await api(`/v1/colleges/${user.college_id}/search?q=${encodeURIComponent(q.trim())}`);
        if (kitchenId) r.results = r.results.filter((g) => g.kitchen.id === kitchenId);
        setRes(r);
        setError(null);
      } catch (e) {
        setError(e);
      }
      setLoading(false);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: space(1.5), paddingTop: space(5), borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable accessibilityRole="button" onPress={nav.pop} style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }} accessibilityLabel="Go back">
          <Text style={{ fontSize: 22 }}>←</Text>
        </Pressable>
        <TextInput autoFocus value={q} onChangeText={setQ} placeholder={kitchenId ? 'Search this kitchen' : 'Search dishes on campus'} placeholderTextColor={colors.faint}
          accessibilityLabel="Search dishes" returnKeyType="search"
          style={{ flex: 1, height: 46, borderRadius: radius.md, backgroundColor: colors.bg, paddingHorizontal: 14, fontSize: 16, color: colors.text }} />
      </View>
      {error ? <ErrorState error={error} onRetry={() => setQ(q + '')} /> : loading && !res ? <ListSkeleton rows={3} /> : !res ? (
        <Empty emoji="🔍" title="Search across every kitchen" subtitle="Try “maggi”, “thali”, “cold coffee”" />
      ) : res.results.length === 0 ? (
        <Empty emoji="🤷" title={`No results for “${res.query}”`} subtitle={res.suggestion ? `Did you mean “${res.suggestion}”?` : 'Check the spelling or try something else'}
          action={res.suggestion ? `Search “${res.suggestion}”` : undefined} onAction={() => setQ(res.suggestion)} />
      ) : (
        <Scroll contentStyle={{ paddingHorizontal: space(2) }}>
          {res.suggestion ? <Text style={[type.small, { marginTop: 12 }]}>Showing results for “{res.suggestion}”</Text> : null}
          {res.results.map((g) => (
            <View key={g.kitchen.id} style={{ marginTop: space(2) }}>
              <Pressable accessibilityRole="button" onPress={() => nav.push('kitchen', { kitchenId: g.kitchen.id })} accessibilityLabel={`Open ${g.kitchen.name}`}>
                <Row style={{ gap: 8 }}>
                  <Text style={{ fontSize: 20 }}>{g.kitchen.emoji}</Text>
                  <Text style={[type.h3, { flex: 1 }]}>{g.kitchen.name}</Text>
                  <Text style={[type.small, { color: g.kitchen.is_open ? colors.green : colors.red, fontWeight: '700' }]}>
                    {g.kitchen.is_open ? `${g.kitchen.prep_minutes} min` : 'Closed'} →
                  </Text>
                </Row>
              </Pressable>
              {g.items.map((it, i) => (
                <View key={it.id}>
                  {i ? <Divider style={{ marginVertical: 0 }} /> : null}
                  <ItemRow item={it} kitchen={g.kitchen} onCustomise={(item) => setSheet({ item, kitchen: g.kitchen })} />
                </View>
              ))}
            </View>
          ))}
        </Scroll>
      )}
      <ItemSheet item={sheet?.item} kitchen={sheet?.kitchen} onClose={() => setSheet(null)} />
    </View>
  );
}

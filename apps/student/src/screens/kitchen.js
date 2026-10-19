import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, SectionList, Text, View } from 'react-native';
import { api } from '../api';
import { useApp } from '../store';
import { colors, radius, rupees, space, type } from '../theme';
import { AddButton, Btn, Chip, Divider, ErrorState, ListSkeleton, Row, Sheet, Stepper, TopBar, VegMark } from '../ui';

export function ItemRow({ item, kitchen, onCustomise, showKitchen }) {
  const { addToCart, qtyOf, decItem, cart, toast, favIds, toggleFavorite } = useApp();
  const qty = qtyOf(item.id);
  const hasOptions = item.addon_groups?.length > 0;
  const closed = kitchen && kitchen.is_open === false;

  const add = async () => {
    if (closed) return toast(kitchen.closed_reason || 'Kitchen is closed right now');
    if (hasOptions) return onCustomise(item);
    await addToCart(kitchen, item);
  };
  const inc = () => {
    if (hasOptions) return onCustomise(item);
    const line = cart.lines.find((l) => l.key === `${item.id}:`);
    if (line && line.quantity >= item.max_per_order) return toast(`Max ${item.max_per_order} per order`);
    addToCart(kitchen, item);
  };

  return (
    <View testID="menu-item" style={{ flexDirection: 'row', paddingVertical: space(2), gap: 12 }}>
      <View style={{ flex: 1 }}>
        <Row style={{ gap: 6, marginBottom: 4 }}>
          <VegMark veg={item.is_veg} />
          {item.is_popular ? <Text style={{ fontSize: 11, fontWeight: '800', color: '#B45309' }}>★ BESTSELLER</Text> : null}
          <View style={{ flex: 1 }} />
          <Pressable onPress={() => toggleFavorite(item.id)} hitSlop={10} accessibilityRole="button"
            accessibilityLabel={favIds.has(item.id) ? `Remove ${item.name} from favourites` : `Save ${item.name} to favourites`}>
            <Text style={{ fontSize: 18, color: favIds.has(item.id) ? colors.red : colors.faint }}>{favIds.has(item.id) ? '♥' : '♡'}</Text>
          </Pressable>
        </Row>
        <Text style={[type.h3, { fontSize: 15 }]} numberOfLines={2}>{item.name}</Text>
        {showKitchen ? <Text style={type.small}>{showKitchen}</Text> : null}
        <Text style={[type.body, { fontWeight: '700', marginTop: 2 }]}>{rupees(item.price_paise)}</Text>
        {item.description ? <Text style={[type.small, { marginTop: 4 }]} numberOfLines={2}>{item.description}</Text> : null}
      </View>
      <View style={{ alignItems: 'center', width: 104 }}>
        <View style={{ width: 96, height: 84, borderRadius: radius.md, backgroundColor: colors.yellowSoft, alignItems: 'center', justifyContent: 'center', opacity: item.sold_out ? 0.5 : 1 }}>
          <Text style={{ fontSize: 40 }} accessibilityLabel="">{item.emoji}</Text>
        </View>
        <View style={{ marginTop: -16 }}>
          <AddButton qty={qty} disabled={item.sold_out} hasOptions={hasOptions} onAdd={add} onInc={inc} onDec={() => decItem(item.id)} />
        </View>
      </View>
    </View>
  );
}

export function ItemSheet({ item, kitchen, onClose }) {
  const { addToCart, toast } = useApp();
  const [picked, setPicked] = useState({});
  const [qty, setQty] = useState(1);

  useEffect(() => {
    if (!item) return;
    // Preselect the first available choice for required single-choice groups (e.g. size).
    const init = {};
    item.addon_groups.forEach((g) => {
      const first = g.choices.find((c) => c.is_available);
      init[g.id] = g.min_select >= 1 && first ? [first.id] : [];
    });
    setPicked(init);
    setQty(1);
  }, [item?.id]);

  if (!item) return null;
  const toggle = (g, c) => {
    const cur = picked[g.id] || [];
    let next;
    if (g.max_select === 1) next = [c.id];
    else if (cur.includes(c.id)) next = cur.filter((x) => x !== c.id);
    else if (cur.length >= g.max_select) return toast(`Choose up to ${g.max_select}`);
    else next = [...cur, c.id];
    setPicked({ ...picked, [g.id]: next });
  };
  const chosen = item.addon_groups.flatMap((g) => g.choices.filter((c) => (picked[g.id] || []).includes(c.id)));
  const unit = item.price_paise + chosen.reduce((n, c) => n + c.price_paise, 0);
  const invalid = item.addon_groups.find((g) => (picked[g.id] || []).length < g.min_select);

  const add = async () => {
    const ok = await addToCart(kitchen, item, {
      quantity: qty,
      choiceIds: chosen.map((c) => c.id),
      optionsLabel: chosen.map((c) => c.name).join(', '),
      unitPrice: unit,
    });
    if (ok) onClose();
  };

  return (
    <Sheet visible={!!item} onClose={onClose}>
      <ScrollView style={{ maxHeight: 460 }}>
        <Row style={{ gap: 12, marginBottom: 12 }}>
          <View style={{ width: 64, height: 64, borderRadius: radius.md, backgroundColor: colors.yellowSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ fontSize: 34 }}>{item.emoji}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Row style={{ gap: 6 }}>
              <VegMark veg={item.is_veg} />
              <Text style={type.h2} numberOfLines={2}>{item.name}</Text>
            </Row>
            <Text style={type.small}>{item.description}</Text>
          </View>
        </Row>
        {item.addon_groups.map((g) => (
          <View key={g.id} style={{ marginBottom: 16 }}>
            <Row style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={type.h3}>{g.name}</Text>
              <Text style={type.small}>{g.min_select ? 'Required' : 'Optional'} · {g.max_select === 1 ? 'pick 1' : `up to ${g.max_select}`}</Text>
            </Row>
            {g.choices.map((c) => {
              const on = (picked[g.id] || []).includes(c.id);
              return (
                <Pressable key={c.id} disabled={!c.is_available} onPress={() => toggle(g, c)}
                  accessibilityRole={g.max_select === 1 ? 'radio' : 'checkbox'} accessibilityState={{ checked: on, disabled: !c.is_available }}
                  style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, opacity: c.is_available ? 1 : 0.4 }}>
                  <View style={{ width: 22, height: 22, borderRadius: g.max_select === 1 ? 11 : 6, borderWidth: 2, borderColor: on ? colors.green : colors.border, alignItems: 'center', justifyContent: 'center', marginRight: 12 }}>
                    {on ? <View style={{ width: 12, height: 12, borderRadius: g.max_select === 1 ? 6 : 3, backgroundColor: colors.green }} /> : null}
                  </View>
                  <Text style={[type.body, { flex: 1 }]}>{c.name}{c.is_available ? '' : ' (unavailable)'}</Text>
                  <Text style={type.small}>{c.price_paise ? `+${rupees(c.price_paise)}` : 'Free'}</Text>
                </Pressable>
              );
            })}
          </View>
        ))}
      </ScrollView>
      <Row style={{ gap: 12, marginTop: 8 }}>
        <Stepper qty={qty} onInc={() => setQty(Math.min(qty + 1, item.max_per_order))} onDec={() => setQty(Math.max(1, qty - 1))} max={item.max_per_order} />
        <Btn title={`Add item · ${rupees(unit * qty)}`} onPress={add} disabled={!!invalid} style={{ flex: 1 }} />
      </Row>
    </Sheet>
  );
}

export function KitchenScreen({ kitchenId, openItemId }) {
  const { nav } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [vegOnly, setVegOnly] = useState(false);
  const [sheetItem, setSheetItem] = useState(null);
  const [activeCat, setActiveCat] = useState(null);
  const listRef = useRef();

  const load = useCallback(async () => {
    try {
      setData(await api(`/v1/kitchens/${kitchenId}/menu`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [kitchenId]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (data && openItemId) {
      const it = data.items.find((i) => i.id === openItemId);
      if (it?.addon_groups?.length) setSheetItem(it);
    }
  }, [data, openItemId]);

  const sections = useMemo(() => {
    if (!data) return [];
    const items = data.items.filter((i) => !vegOnly || i.is_veg);
    const out = data.categories
      .map((c) => ({ id: c.id, title: c.name, data: items.filter((i) => i.category_id === c.id) }))
      .filter((s) => s.data.length);
    const loose = items.filter((i) => !data.categories.some((c) => c.id === i.category_id));
    if (loose.length) out.push({ id: 0, title: 'More', data: loose });
    return out;
  }, [data, vegOnly]);

  if (error) return (<View style={{ flex: 1, backgroundColor: colors.surface }}><TopBar title="Kitchen" onBack={nav.pop} /><ErrorState error={error} onRetry={load} /></View>);
  if (!data) return (<View style={{ flex: 1, backgroundColor: colors.surface }}><TopBar title="Loading…" onBack={nav.pop} /><ListSkeleton rows={5} /></View>);
  const k = data.kitchen;

  const header = (
    <View>
      <View style={{ backgroundColor: colors.yellowSoft, padding: space(2.5), borderBottomLeftRadius: 24, borderBottomRightRadius: 24 }}>
        <Row style={{ gap: 14 }}>
          <View style={{ width: 64, height: 64, borderRadius: 18, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ fontSize: 36 }}>{k.emoji}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={type.h2}>{k.name}</Text>
            <Text style={type.small}>{k.cuisine}</Text>
          </View>
          {k.rating ? (
            <View style={{ backgroundColor: colors.green, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 }}>
              <Text style={{ color: '#fff', fontWeight: '800' }}>★ {k.rating}</Text>
            </View>
          ) : null}
        </Row>
        <Row style={{ gap: 16, marginTop: 14, flexWrap: 'wrap' }}>
          <Text style={[type.small, { color: colors.text, fontWeight: '600' }]}>⏱ ~{k.prep_minutes} min</Text>
          <Text style={[type.small, { color: colors.text, fontWeight: '600' }]}>📍 {k.counter_location || 'Pickup counter'}</Text>
          <Text style={[type.small, { color: colors.text, fontWeight: '600' }]}>🕘 {k.opens_at ? `Today ${k.opens_at}–${k.closes_at}` : 'Closed today'}</Text>
        </Row>
        {!k.is_open ? (
          <View style={{ backgroundColor: colors.redSoft, padding: 10, borderRadius: 10, marginTop: 12 }}>
            <Text style={{ color: colors.red, fontWeight: '700' }}>{k.closed_reason}</Text>
            <Text style={type.small}>You can browse the menu, but ordering is paused.</Text>
          </View>
        ) : k.busy_mode ? (
          <View style={{ backgroundColor: colors.yellow, padding: 10, borderRadius: 10, marginTop: 12 }}>
            <Text style={{ fontWeight: '700' }}>🔥 Busy right now — orders may take a little longer</Text>
          </View>
        ) : null}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, padding: space(2) }}>
        <Chip label="🟢 Veg only" active={vegOnly} onPress={() => setVegOnly(!vegOnly)} />
        {sections.map((sec, idx) => (
          <Chip key={sec.id} label={sec.title} active={activeCat === sec.id}
            onPress={() => {
              setActiveCat(sec.id);
              listRef.current?.scrollToLocation({ sectionIndex: idx, itemIndex: 0, viewOffset: 40, animated: true });
            }} />
        ))}
      </ScrollView>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <TopBar title={k.name} subtitle={k.is_open ? `Open · ready in ~${k.prep_minutes} min` : 'Closed'} onBack={nav.pop}
        right={<Pressable accessibilityRole="button" onPress={() => nav.push('search', { kitchenId: k.id })} accessibilityLabel="Search this kitchen" hitSlop={10}><Text style={{ fontSize: 20 }}>🔍</Text></Pressable>} />
      <SectionList
        ref={listRef}
        sections={sections}
        keyExtractor={(i) => String(i.id)}
        ListHeaderComponent={header}
        stickySectionHeadersEnabled
        initialNumToRender={12}
        onScrollToIndexFailed={() => {}}
        contentContainerStyle={{ paddingBottom: 140 }}
        renderSectionHeader={({ section }) => (
          <View style={{ backgroundColor: colors.surface, paddingHorizontal: space(2), paddingTop: space(2), paddingBottom: 4 }}>
            <Text style={type.h3}>{section.title} <Text style={type.small}>({section.data.length})</Text></Text>
          </View>
        )}
        ItemSeparatorComponent={() => <Divider style={{ marginVertical: 0, marginHorizontal: space(2) }} />}
        renderItem={({ item }) => (
          <View style={{ paddingHorizontal: space(2) }}>
            <ItemRow item={item} kitchen={k} onCustomise={setSheetItem} />
          </View>
        )}
        ListEmptyComponent={<Text style={[type.small, { textAlign: 'center', padding: 24 }]}>No items match this filter.</Text>}
      />
      <ItemSheet item={sheetItem} kitchen={k} onClose={() => setSheetItem(null)} />
    </View>
  );
}

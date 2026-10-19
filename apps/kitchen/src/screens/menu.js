import { useCallback, useEffect, useState } from 'react';
import { Pressable, SectionList, Switch, Text, TextInput, View } from 'react-native';
import { api } from '../api';
import { useKitchen } from '../store';
import { colors, radius, rupees, space, type } from '../theme';
import { Btn, Card, Chip, Divider, ErrorState, Field, ListSkeleton, Row, Scroll, Sheet, TopBar, VegMark } from '../ui';

const toRupees = (p) => (p == null ? '' : String(p / 100));
const toPaise = (r) => Math.round(parseFloat(r || '0') * 100);

function AddonEditor({ groups, onChange }) {
  const update = (gi, patch) => onChange(groups.map((g, i) => (i === gi ? { ...g, ...patch } : g)));
  const updateChoice = (gi, ci, patch) =>
    update(gi, { choices: groups[gi].choices.map((c, i) => (i === ci ? { ...c, ...patch } : c)) });
  return (
    <View style={{ gap: 12 }}>
      {groups.map((g, gi) => (
        <View key={gi} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12 }}>
          <Row style={{ gap: 8 }}>
            <TextInput value={g.name} onChangeText={(v) => update(gi, { name: v })} placeholder="Group name (e.g. Size)"
              style={{ flex: 1, fontWeight: '700', fontSize: 15, color: colors.text, paddingVertical: 6 }} accessibilityLabel="Option group name" />
            <Pressable accessibilityRole="button" onPress={() => onChange(groups.filter((_, i) => i !== gi))} hitSlop={8} accessibilityLabel="Remove group">
              <Text style={{ color: colors.red, fontWeight: '700' }}>Remove</Text>
            </Pressable>
          </Row>
          <Row style={{ gap: 8, marginVertical: 8 }}>
            <Chip label="Required · pick 1" active={g.min_select === 1 && g.max_select === 1} onPress={() => update(gi, { min_select: 1, max_select: 1 })} />
            <Chip label="Optional · up to 3" active={g.min_select === 0} onPress={() => update(gi, { min_select: 0, max_select: 3 })} />
          </Row>
          {g.choices.map((c, ci) => (
            <Row key={ci} style={{ gap: 8, marginBottom: 6 }}>
              <TextInput value={c.name} onChangeText={(v) => updateChoice(gi, ci, { name: v })} placeholder="Choice"
                style={{ flex: 2, borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, height: 40, color: colors.text }} accessibilityLabel="Choice name" />
              <TextInput value={c.price} onChangeText={(v) => updateChoice(gi, ci, { price: v.replace(/[^\d.]/g, '') })} placeholder="+₹" keyboardType="decimal-pad"
                style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, height: 40, color: colors.text }} accessibilityLabel="Extra price in rupees" />
              <Pressable accessibilityRole="button" onPress={() => update(gi, { choices: g.choices.filter((_, i) => i !== ci) })} hitSlop={8} accessibilityLabel="Remove choice">
                <Text style={{ fontSize: 18, color: colors.faint }}>✕</Text>
              </Pressable>
            </Row>
          ))}
          <Pressable accessibilityRole="button" onPress={() => update(gi, { choices: [...g.choices, { name: '', price: '' }] })}>
            <Text style={{ color: colors.green, fontWeight: '700', marginTop: 4 }}>+ Add choice</Text>
          </Pressable>
        </View>
      ))}
      <Btn title="Add option group (size, extras…)" variant="secondary" small
        onPress={() => onChange([...groups, { name: '', min_select: 0, max_select: 3, choices: [{ name: '', price: '' }] }])} />
    </View>
  );
}

function ItemEditor({ item, categories, onClose, onSaved }) {
  const { kitchenId, toast, confirm } = useKitchen();
  const isNew = !item.id;
  const [f, setF] = useState({
    name: item.name || '',
    price: toRupees(item.price_paise),
    category_id: item.category_id ?? categories[0]?.id ?? null,
    is_veg: item.is_veg ?? true,
    emoji: item.emoji || '🍲',
    description: item.description || '',
    unlimited: item.stock_qty == null,
    stock: item.stock_qty == null ? '' : String(item.stock_qty),
    max_per_order: String(item.max_per_order || 10),
    is_popular: !!item.is_popular,
    is_available: item.is_available ?? true,
    groups: (item.addon_groups || []).map((g) => ({
      name: g.name, min_select: g.min_select, max_select: g.max_select,
      choices: g.choices.map((c) => ({ name: c.name, price: toRupees(c.price_paise), is_available: c.is_available })),
    })),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (v) => setF({ ...f, [k]: v });

  const save = async () => {
    setError(null);
    if (!f.name.trim()) return setError('Name is required');
    if (!(parseFloat(f.price) >= 0)) return setError('Enter a valid price');
    const groups = f.groups
      .map((g) => ({ ...g, choices: g.choices.filter((c) => c.name.trim()) }))
      .filter((g) => g.name.trim() && g.choices.length);
    const body = {
      name: f.name.trim(), price_paise: toPaise(f.price), category_id: f.category_id, is_veg: f.is_veg, emoji: f.emoji || '🍲',
      description: f.description, max_per_order: parseInt(f.max_per_order, 10) || 10, is_popular: f.is_popular, is_available: f.is_available,
      addon_groups: groups.map((g) => ({
        name: g.name.trim(), min_select: g.min_select, max_select: Math.min(g.max_select, g.choices.length) || 1,
        choices: g.choices.map((c) => ({ name: c.name.trim(), price_paise: toPaise(c.price), is_available: c.is_available ?? true })),
      })),
    };
    if (isNew) body.stock_qty = f.unlimited ? null : parseInt(f.stock || '0', 10);
    else if (f.unlimited) body.unlimited_stock = true;
    else body.stock_qty = parseInt(f.stock || '0', 10);
    setBusy(true);
    try {
      await api(isNew ? `/v1/kitchen/kitchens/${kitchenId}/menu-items` : `/v1/kitchen/menu-items/${item.id}`, { method: isNew ? 'POST' : 'PATCH', body });
      toast(isNew ? 'Item added to menu' : 'Item updated', 'success');
      onSaved();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };

  const remove = async () => {
    if (!(await confirm({ title: `Delete ${item.name}?`, message: 'It disappears from the menu. Past orders keep their details.', confirmText: 'Delete', destructive: true }))) return;
    try {
      await api(`/v1/kitchen/menu-items/${item.id}`, { method: 'DELETE' });
      toast('Item deleted');
      onSaved();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title={isNew ? 'Add menu item' : 'Edit item'} onBack={onClose} />
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        <Card>
          <Row style={{ gap: 12, alignItems: 'flex-start' }}>
            <Field label="Icon" value={f.emoji} onChangeText={set('emoji')} maxLength={4} style={{ width: 72 }} inputStyle={{ fontSize: 26, textAlign: 'center' }} />
            <Field label="Item name *" value={f.name} onChangeText={set('name')} style={{ flex: 1 }} />
          </Row>
          <Row style={{ gap: 12 }}>
            <Field label="Price (₹) *" value={f.price} onChangeText={(v) => set('price')(v.replace(/[^\d.]/g, ''))} keyboardType="decimal-pad" style={{ flex: 1 }} />
            <Field label="Max per order" value={f.max_per_order} onChangeText={(v) => set('max_per_order')(v.replace(/\D/g, ''))} keyboardType="number-pad" style={{ flex: 1 }} />
          </Row>
          <Field label="Description" value={f.description} onChangeText={set('description')} />
          <Text style={[type.small, { fontWeight: '600', color: colors.text, marginBottom: 8 }]}>Category</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {categories.map((c) => <Chip key={c.id} label={c.name} active={f.category_id === c.id} onPress={() => set('category_id')(c.id)} />)}
          </View>
          <Row style={{ gap: 8 }}>
            <Chip label="🟢 Veg" active={f.is_veg} onPress={() => set('is_veg')(true)} />
            <Chip label="🔴 Non-veg" active={!f.is_veg} onPress={() => set('is_veg')(false)} />
            <Chip label="★ Bestseller" active={f.is_popular} onPress={() => set('is_popular')(!f.is_popular)} />
          </Row>
        </Card>
        <Card>
          <Text style={[type.h3, { marginBottom: 10 }]}>Stock</Text>
          <Row style={{ justifyContent: 'space-between', marginBottom: 10 }}>
            <Text style={type.body}>Available to order</Text>
            <Switch value={f.is_available} onValueChange={set('is_available')} trackColor={{ true: colors.green }} accessibilityLabel="Available to order" />
          </Row>
          <Row style={{ gap: 8, marginBottom: 10 }}>
            <Chip label="Unlimited" active={f.unlimited} onPress={() => set('unlimited')(true)} />
            <Chip label="Limited portions" active={!f.unlimited} onPress={() => set('unlimited')(false)} />
          </Row>
          {!f.unlimited ? <Field label="Portions left" value={f.stock} onChangeText={(v) => set('stock')(v.replace(/\D/g, ''))} keyboardType="number-pad" /> : null}
        </Card>
        <Card>
          <Text style={[type.h3, { marginBottom: 10 }]}>Sizes & add-ons</Text>
          <AddonEditor groups={f.groups} onChange={set('groups')} />
        </Card>
        {error ? <Text style={{ color: colors.red }}>{error}</Text> : null}
        <Btn title={isNew ? 'Publish item' : 'Save changes'} onPress={save} loading={busy} />
        {!isNew ? <Btn title="Delete item" variant="danger" onPress={remove} /> : null}
      </Scroll>
    </View>
  );
}

export function MenuScreen() {
  const { kitchenId, can, toast } = useKitchen();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [catSheet, setCatSheet] = useState(false);
  const [catName, setCatName] = useState('');
  const [stockFor, setStockFor] = useState(null);
  const [stockVal, setStockVal] = useState('');
  const [q, setQ] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api(`/v1/kitchen/kitchens/${kitchenId}/menu`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [kitchenId]);
  useEffect(() => { load(); }, [load]);

  const patch = async (item, body, msg) => {
    try {
      await api(`/v1/kitchen/menu-items/${item.id}`, { method: 'PATCH', body });
      if (msg) toast(msg);
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  const addCategory = async () => {
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}/categories`, { method: 'POST', body: { name: catName.trim(), sort_order: data.categories.length } });
      setCatName('');
      setCatSheet(false);
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  if (editing) return <ItemEditor item={editing} categories={data.categories} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />;
  if (error) return <ErrorState error={error} onRetry={load} />;
  if (!data) return <View style={{ flex: 1, paddingTop: space(5) }}><ListSkeleton rows={6} /></View>;

  const match = (i) => !q || i.name.toLowerCase().includes(q.toLowerCase());
  const sections = data.categories.map((c) => ({ title: c.name, data: data.items.filter((i) => i.category_id === c.id && match(i)) }));
  const loose = data.items.filter((i) => !data.categories.some((c) => c.id === i.category_id) && match(i));
  if (loose.length) sections.push({ title: 'Uncategorised', data: loose });
  const soldOut = data.items.filter((i) => i.sold_out).length;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.surface, paddingTop: space(5), padding: space(2), borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Row style={{ justifyContent: 'space-between' }}>
          <View>
            <Text style={type.h1}>Menu</Text>
            <Text style={type.small}>{data.items.length} items · {soldOut} sold out</Text>
          </View>
          {can.manage ? (
            <Row style={{ gap: 8 }}>
              <Btn title="+ Category" small variant="secondary" onPress={() => setCatSheet(true)} />
              <Btn title="+ Item" small onPress={() => setEditing({})} disabled={!data.categories.length} />
            </Row>
          ) : null}
        </Row>
        <TextInput value={q} onChangeText={setQ} placeholder="🔍  Find an item" placeholderTextColor={colors.faint} accessibilityLabel="Find an item"
          style={{ height: 44, borderRadius: radius.md, backgroundColor: colors.bg, paddingHorizontal: 14, marginTop: 12, color: colors.text }} />
      </View>
      <SectionList
        sections={sections}
        keyExtractor={(i) => String(i.id)}
        contentContainerStyle={{ paddingBottom: 100 }}
        stickySectionHeadersEnabled
        renderSectionHeader={({ section }) => (
          <View style={{ backgroundColor: colors.bg, paddingHorizontal: space(2), paddingTop: space(2), paddingBottom: 6 }}>
            <Text style={type.label}>{section.title} · {section.data.length}</Text>
          </View>
        )}
        renderItem={({ item }) => (
          <View testID="menu-row" style={{ backgroundColor: colors.surface, paddingHorizontal: space(2), paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <Row style={{ gap: 12 }}>
              <Text style={{ fontSize: 28, opacity: item.sold_out ? 0.4 : 1 }}>{item.emoji}</Text>
              {/* Siblings, not nested: on web a nested press would also open the editor. */}
              <View style={{ flex: 1 }}>
                <Pressable accessibilityRole="button" disabled={!can.manage} onPress={() => setEditing(item)}
                  accessibilityLabel={can.manage ? `Edit ${item.name}` : item.name}>
                  <Row style={{ gap: 6 }}>
                    <VegMark veg={item.is_veg} size={12} />
                    <Text style={[type.h3, { fontSize: 15 }]} numberOfLines={1}>{item.name}</Text>
                  </Row>
                  <Text style={type.small}>
                    {rupees(item.price_paise)}
                    {item.addon_groups.length ? ` · ${item.addon_groups.length} option group${item.addon_groups.length > 1 ? 's' : ''}` : ''}
                  </Text>
                </Pressable>
                <Pressable accessibilityRole="button" style={{ alignSelf: 'flex-start' }} hitSlop={6}
                  onPress={() => { setStockFor(item); setStockVal(item.stock_qty == null ? '' : String(item.stock_qty)); }}>
                  <Text style={[type.small, { fontWeight: '700', color: item.stock_qty === 0 ? colors.red : item.stock_qty != null ? '#9A6700' : colors.green }]}>
                    {item.stock_qty == null ? '∞ Unlimited stock' : `${item.stock_qty} portions left`} · edit
                  </Text>
                </Pressable>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Switch value={item.is_available} onValueChange={(v) => patch(item, { is_available: v }, v ? `${item.name} is back on` : `${item.name} marked sold out`)}
                  trackColor={{ true: colors.green }} accessibilityLabel={`${item.name} available`} />
                <Text style={{ fontSize: 10, color: colors.muted }}>{item.is_available ? 'In stock' : 'Sold out'}</Text>
              </View>
            </Row>
          </View>
        )}
        ListEmptyComponent={<Text style={[type.small, { textAlign: 'center', padding: 32 }]}>{data.categories.length ? 'No items yet. Tap “+ Item”.' : 'Start by adding a category, e.g. “Snacks”.'}</Text>}
      />

      <Sheet visible={catSheet} onClose={() => setCatSheet(false)} title="New category">
        <Field placeholder="e.g. Beverages" value={catName} onChangeText={setCatName} autoFocus />
        <Btn title="Add category" onPress={addCategory} disabled={!catName.trim()} />
      </Sheet>

      <Sheet visible={!!stockFor} onClose={() => setStockFor(null)} title={`Stock · ${stockFor?.name}`}>
        <Field label="Portions left (leave empty for unlimited)" value={stockVal} onChangeText={(v) => setStockVal(v.replace(/\D/g, ''))} keyboardType="number-pad" autoFocus />
        <Row style={{ gap: 10 }}>
          <Btn title="Set unlimited" variant="secondary" style={{ flex: 1 }} onPress={() => { patch(stockFor, { unlimited_stock: true }, 'Stock set to unlimited'); setStockFor(null); }} />
          <Btn title="Save" style={{ flex: 1 }} disabled={stockVal === ''} onPress={() => { patch(stockFor, { stock_qty: parseInt(stockVal, 10) }, 'Stock updated'); setStockFor(null); }} />
        </Row>
      </Sheet>
    </View>
  );
}

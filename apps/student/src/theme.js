// CampusBite design tokens — starting point from the PRD (§07), not fixed brand rules.
export const colors = {
  yellow: '#F8C81C',
  yellowSoft: '#FFF7D9',
  green: '#166534',
  greenMid: '#1F7A45',
  greenSoft: '#E7F4EC',
  bg: '#F5F6F3',
  surface: '#FFFFFF',
  text: '#1B1E1C',
  muted: '#68706B',
  faint: '#9AA19C',
  border: '#E4E7E2',
  red: '#B42318',
  redSoft: '#FDECEA',
  blue: '#1D4ED8',
  blueSoft: '#E8EEFD',
  veg: '#1E8E3E',
  nonveg: '#B3261E',
  overlay: 'rgba(16, 24, 20, 0.45)',
};

export const radius = { sm: 8, md: 12, lg: 16, xl: 24, pill: 999 };
export const space = (n) => n * 8;

export const type = {
  h1: { fontSize: 26, fontWeight: '800', color: colors.text, letterSpacing: -0.4 },
  h2: { fontSize: 20, fontWeight: '800', color: colors.text, letterSpacing: -0.2 },
  h3: { fontSize: 16, fontWeight: '700', color: colors.text },
  body: { fontSize: 14, color: colors.text, lineHeight: 20 },
  small: { fontSize: 12, color: colors.muted, lineHeight: 16 },
  label: { fontSize: 12, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.6 },
};

export const shadow = {
  shadowColor: '#0B1F14',
  shadowOpacity: 0.08,
  shadowRadius: 12,
  shadowOffset: { width: 0, height: 4 },
  elevation: 3,
};

export const rupees = (paise) => {
  const r = (paise || 0) / 100;
  return '₹' + (Number.isInteger(r) ? r.toString() : r.toFixed(2));
};

export const STATUS = {
  PENDING_ACCEPTANCE: { label: 'Waiting for kitchen', color: colors.blue, bg: colors.blueSoft, icon: '⏳' },
  ACCEPTED: { label: 'Accepted', color: colors.green, bg: colors.greenSoft, icon: '👍' },
  PREPARING: { label: 'Preparing', color: '#9A6700', bg: colors.yellowSoft, icon: '👨‍🍳' },
  READY: { label: 'Ready for pickup', color: '#FFFFFF', bg: colors.green, icon: '✅' },
  COMPLETED: { label: 'Collected', color: colors.muted, bg: '#EEF0ED', icon: '🎉' },
  REJECTED: { label: 'Rejected', color: colors.red, bg: colors.redSoft, icon: '✖' },
  CANCELLED: { label: 'Cancelled', color: colors.red, bg: colors.redSoft, icon: '✖' },
};

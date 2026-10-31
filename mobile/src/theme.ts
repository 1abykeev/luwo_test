// Design tokens taken from luwo.ai's own stylesheet (lw-* colors, Oswald + Inter, pill shapes).

export const colors = {
  navy: '#121d39',
  indigo: '#19284c',
  ink: '#111a3c',
  steel: '#235479',
  cyan: '#01c3ff',
  teal: '#16abd9',
  periwinkle: '#7aa6ff',
  sky: '#b2deff',
  fog: '#e5edf2',
  white: '#ffffff',
  muted: '#6b7a99',
  line: '#d5dfe8',
  ok: '#00b981',
  okBg: '#ecfdf5',
  okText: '#006b4a',
  okBorder: '#b9f8cf',
  err: '#e40016',
  errBg: '#fff0f1',
  errBorder: '#ffc9cd',
  warn: '#b7791f',
  warnBg: '#fff7e6',
} as const;

export const fonts = {
  display: 'Oswald_600SemiBold',
  displayMedium: 'Oswald_500Medium',
  displayBold: 'Oswald_700Bold',
  body: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemibold: 'Inter_600SemiBold',
} as const;

export const radius = {
  pill: 999,
  card: 22,
  bubble: 20,
  small: 14,
} as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;

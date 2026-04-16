// src/theme.js
export const modernTheme = {
  name: '朦胧凝光',
  light: {
    custom: { 
      '--global-bg': 'linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%)', 
      '--sider-bg': 'rgba(255, 255, 255, 0.4)',
      '--card-bg-color': 'rgba(255, 255, 255, 0.65)', 
      '--modal-solid-bg-color': '#ffffff', 
      '--card-border-color': 'rgba(255, 255, 255, 0.8)', 
      '--card-shadow-color': 'rgba(0, 0, 0, 0.03)', 
      '--accent-color': '#4A90E2', 
      '--accent-glow-color': 'rgba(74, 144, 226, 0.15)', 
      '--text-color': '#333639' 
    },
    naive: { 
      common: { primaryColor: '#4A90E2', primaryColorHover: '#5B9DE5', primaryColorPressed: '#3A80D2', bodyColor: 'transparent', modalColor: '#ffffff', popoverColor: '#ffffff' }, 
      Card: { color: 'rgba(255, 255, 255, 0.65)', borderColor: 'rgba(255, 255, 255, 0.8)' }, 
      Layout: { siderColor: 'transparent', color: 'transparent', headerColor: 'transparent' }, 
      Menu: { itemTextColor: '#555a5f', itemIconColor: '#555a5f', itemTextColorActive: 'var(--n-common-primary-color)', itemIconColorActive: 'var(--n-common-primary-color)' },
      Drawer: { color: '#ffffff' },
      Dialog: { color: '#ffffff' }
    }
  },
  dark: {
    custom: { 
      '--global-bg': 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)', 
      '--sider-bg': 'rgba(15, 23, 42, 0.4)',
      '--card-bg-color': 'rgba(30, 41, 59, 0.5)', 
      '--modal-solid-bg-color': '#1e293b', 
      '--card-border-color': 'rgba(255, 255, 255, 0.08)', 
      '--card-shadow-color': 'rgba(0, 0, 0, 0.25)', 
      '--accent-color': '#8ca8f9', 
      '--accent-glow-color': 'rgba(140, 168, 249, 0.2)', 
      '--text-color': '#e2e8f0' 
    },
    naive: {
      common: { primaryColor: '#8ca8f9', primaryColorHover: '#a3bdfc', primaryColorPressed: '#7090e8', primaryColorSuppl: '#8ca8f9', bodyColor: 'transparent', cardColor: 'rgba(30, 41, 59, 0.5)', modalColor: '#1e293b', popoverColor: '#1e293b' },
      Card: { color: 'rgba(30, 41, 59, 0.5)', borderColor: 'rgba(255, 255, 255, 0.08)' }, 
      Layout: { siderColor: 'transparent', color: 'transparent', headerColor: 'transparent' }, 
      Menu: { itemTextColor: '#94a3b8', itemIconColor: '#94a3b8', itemTextColorActive: 'var(--n-common-primary-color)', itemIconColorActive: 'var(--n-common-primary-color)' },
      Switch: { railColorActive: '#8ca8f9' }, 
      Slider: { fillColor: '#8ca8f9' }, 
      Checkbox: { colorChecked: '#8ca8f9', checkMarkColor: '#0f172a', borderChecked: '#8ca8f9' }, 
      Button: { textColorPrimary: '#0f172a' },
      Drawer: { color: '#1e293b' },
      Dialog: { color: '#1e293b' }
    }
  }
};
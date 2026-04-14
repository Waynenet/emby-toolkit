// src/theme.js

export const modernTheme = {
  name: '现代极简',
  light: {
    custom: { '--card-bg-color': '#ffffff', '--modal-solid-bg-color': '#ffffff', '--card-border-color': 'rgba(0, 0, 0, 0.08)', '--card-shadow-color': 'rgba(0, 0, 0, 0.04)', '--accent-color': '#2080f0', '--accent-glow-color': 'rgba(32, 128, 240, 0.2)', '--text-color': '#333639' },
    naive: { 
      common: { primaryColor: '#2080f0', bodyColor: '#f3f4f6' }, 
      Card: { color: '#ffffff', borderColor: 'rgba(0, 0, 0, 0.08)' }, 
      Layout: { siderColor: '#ffffff' }, 
      Menu: { itemTextColor: '#333639', itemIconColor: '#333639', itemTextColorActive: 'var(--n-common-primary-color)', itemIconColorActive: 'var(--n-common-primary-color)' } 
    }
  },
  dark: {
    custom: { '--card-bg-color': '#18181c', '--modal-solid-bg-color': '#18181c', '--card-border-color': 'rgba(255, 255, 255, 0.09)', '--card-shadow-color': 'rgba(0, 0, 0, 0.2)', '--accent-color': '#70c0e8', '--accent-glow-color': 'rgba(112, 192, 232, 0.3)', '--text-color': '#ffffff' },
    naive: {
      common: { primaryColor: '#70c0e8', primaryColorHover: '#8acbec', primaryColorPressed: '#66afd3', primaryColorSuppl: '#70c0e8', bodyColor: '#101014', cardColor: '#18181c' },
      Card: { color: '#18181c', borderColor: 'rgba(255, 255, 255, 0.09)' }, 
      Layout: { siderColor: '#101014' }, 
      Menu: { itemTextColor: '#a3a6ad', itemIconColor: '#a3a6ad', itemTextColorActive: 'var(--n-common-primary-color)', itemIconColorActive: 'var(--n-common-primary-color)' },
      Switch: { railColorActive: '#70c0e8' }, 
      Slider: { fillColor: '#70c0e8' }, 
      Checkbox: { colorChecked: '#70c0e8', checkMarkColor: '#101014', borderChecked: '#70c0e8' }, 
      Button: { textColorPrimary: '#101014' }
    }
  }
};
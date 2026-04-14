// src/theme.js

export const appTheme = {
  light: {
    custom: {
      '--card-bg-color': 'rgba(255, 255, 255, 0.85)',
      '--modal-solid-bg-color': 'rgb(255, 255, 255)',
      '--card-border-color': 'rgba(0, 0, 0, 0.1)',
      '--card-shadow-color': 'rgba(0, 0, 0, 0.08)',
      '--accent-color': '#007aff',
      '--accent-glow-color': 'rgba(0, 122, 255, 0.2)',
      '--text-color': '#1a1a1a'
    },
    naive: {
      common: { primaryColor: '#007aff', bodyColor: '#f0f2f5' },
      Card: { color: 'rgba(255, 255, 255, 0.85)', borderColor: 'rgba(0, 0, 0, 0.1)' },
      Layout: { siderColor: '#f5f7fa' },
      Menu: {
        itemTextColor: '#4c5b6a',
        itemIconColor: '#4c5b6a',
        itemTextColorHover: 'var(--n-common-primary-color)',
        itemIconColorHover: 'var(--n-common-primary-color)',
        itemTextColorActive: 'var(--n-common-primary-color)',
        itemIconColorActive: 'var(--n-common-primary-color)',
        itemTextColorActiveHover: 'var(--n-common-primary-color)',
        itemIconColorActiveHover: 'var(--n-common-primary-color)'
      }
    }
  },
  dark: {
    custom: {
      '--card-bg-color': 'rgba(26, 27, 30, 0.7)',
      '--modal-solid-bg-color': 'rgb(26, 27, 30)',
      '--card-border-color': 'rgba(255, 255, 255, 0.1)',
      '--card-shadow-color': 'rgba(0, 0, 0, 0.3)',
      '--accent-color': '#00a1ff',
      '--accent-glow-color': 'rgba(0, 161, 255, 0.4)',
      '--text-color': '#ffffff'
    },
    naive: {
      common: {
        primaryColor: '#00a1ff',
        primaryColorHover: '#33b4ff',
        primaryColorPressed: '#0090e6',
        primaryColorSuppl: '#00a1ff',
        bodyColor: '#101014',
        cardColor: 'rgba(26, 27, 30, 0.7)'
      },
      Card: { color: 'rgba(26, 27, 30, 0.7)', borderColor: 'rgba(255, 255, 255, 0.1)' },
      Layout: { siderColor: '#101418' },
      Menu: {
        itemTextColor: '#a8aeb3',
        itemIconColor: '#a8aeb3',
        itemTextColorHover: '#ffffff',
        itemIconColorHover: '#ffffff',
        itemTextColorActive: 'var(--n-common-primary-color)',
        itemIconColorActive: 'var(--n-common-primary-color)',
        itemTextColorActiveHover: 'var(--n-common-primary-color)',
        itemIconColorActiveHover: 'var(--n-common-primary-color)'
      },
      Switch: { railColorActive: '#00a1ff' },
      Slider: { fillColor: '#00a1ff' },
      Checkbox: { colorChecked: '#00a1ff', checkMarkColor: '#ffffff', borderChecked: '#00a1ff' },
      Button: { textColorPrimary: '#ffffff' }
    }
  }
};

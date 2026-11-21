import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'ai.auren.personal',
  appName: 'AUREN',
  webDir: 'dist',
  bundledWebRuntime: false,
  backgroundColor: '#08090c',
  server: {
    androidScheme: 'https',
    cleartext: false,
  },
  plugins: {
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#08090c',
      overlaysWebView: false,
    },
    Keyboard: {
      resize: 'body',
      style: 'DARK',
      resizeOnFullScreen: true,
    },
    App: {
      deepLinking: {
        scheme: 'auren',
      },
    },
  },
};

export default config;


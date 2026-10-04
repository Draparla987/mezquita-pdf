import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'es.mezquitapdf.app',
  appName: 'Mezquita PDF',
  webDir: 'dist',
  backgroundColor: '#FBF8F4',
  ios: {
    contentInset: 'never',
    backgroundColor: '#FBF8F4',
    scheme: 'Mezquita PDF',
  },
};

export default config;

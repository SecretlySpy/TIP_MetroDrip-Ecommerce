module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        'module-resolver',
        {
          alias: { '@': './src' },
        },
      ],
      // Reanimated's plugin MUST be last. React Navigation pulls Reanimated in
      // through react-native-screens, and Expo Go initialises its native
      // ReanimatedPackage unconditionally — without this plugin the native
      // UIManager fails to construct and the app dies on first render with
      // "Failed to create NativeModule 'UIManager'".
      'react-native-reanimated/plugin',
    ],
  };
};

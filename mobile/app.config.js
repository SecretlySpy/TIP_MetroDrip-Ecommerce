/**
 * Keep the declarative native configuration in app.json, but fail EAS
 * distribution builds before compilation when their public API endpoint has
 * not been configured in the selected EAS environment.
 */
module.exports = ({ config }) => {
  const profile = process.env.EAS_BUILD_PROFILE;
  if (
    (profile === 'preview' || profile === 'production') &&
    !process.env.EXPO_PUBLIC_API_URL
  ) {
    throw new Error(
      `EXPO_PUBLIC_API_URL must be configured for the EAS ${profile} environment.`,
    );
  }

  return config;
};

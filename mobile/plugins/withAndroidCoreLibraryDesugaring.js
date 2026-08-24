const { withAppBuildGradle } = require('expo/config-plugins');

const COMPILE_MARKER = '// MetroDrip: support Java time APIs on Android API 24-25.';
const DEPENDENCY_MARKER = '// MetroDrip: desugared Java APIs for the API 24 minimum.';

module.exports = function withAndroidCoreLibraryDesugaring(config) {
  return withAppBuildGradle(config, (modConfig) => {
    if (modConfig.modResults.language !== 'groovy') {
      throw new Error('MetroDrip core-library desugaring requires a Groovy app build.gradle.');
    }

    let contents = modConfig.modResults.contents;

    if (!contents.includes(COMPILE_MARKER)) {
      const compileSdkLine = '    compileSdk rootProject.ext.compileSdkVersion';
      if (!contents.includes(compileSdkLine)) {
        throw new Error('Could not locate compileSdk in the generated Android app build.gradle.');
      }
      contents = contents.replace(
        compileSdkLine,
        `${compileSdkLine}\n\n    ${COMPILE_MARKER}\n    compileOptions {\n        coreLibraryDesugaringEnabled true\n    }`,
      );
    }

    if (!contents.includes(DEPENDENCY_MARKER)) {
      const dependenciesBlock = 'dependencies {';
      if (!contents.includes(dependenciesBlock)) {
        throw new Error('Could not locate dependencies in the generated Android app build.gradle.');
      }
      contents = contents.replace(
        dependenciesBlock,
        `${dependenciesBlock}\n    ${DEPENDENCY_MARKER}\n    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.3")`,
      );
    }

    modConfig.modResults.contents = contents;
    return modConfig;
  });
};

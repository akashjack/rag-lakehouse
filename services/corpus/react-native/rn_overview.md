# React Native Overview

React Native is an open-source framework for building mobile applications using React and JavaScript. It allows developers to build truly native mobile apps for iOS and Android using a single codebase.

## Core Concepts

### Components
React Native apps are built with components. Components are the building blocks of any React Native application. They describe what should appear on the screen.

### Native Modules
React Native bridges JavaScript and native code. Native modules allow JavaScript to call native platform APIs and vice versa.

### StyleSheet
React Native uses a StyleSheet API similar to CSS but adapted for mobile. Styles are written in JavaScript objects.

```javascript
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
```

## Key Differences from React

- Uses native components instead of DOM elements
- Uses Flexbox for layout (similar to web)
- No CSS — uses JavaScript style objects
- Navigation is handled differently (React Navigation library)
- Platform-specific code via Platform.OS

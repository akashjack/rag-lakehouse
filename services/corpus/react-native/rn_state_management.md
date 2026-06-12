# React Native State Management

State management in React Native follows the same patterns as React.

## useState Hook

```javascript
import React, { useState } from 'react';
import { View, Text, Button } from 'react-native';

function Counter() {
  const [count, setCount] = useState(0);
  return (
    <View>
      <Text>Count: {count}</Text>
      <Button title="Increment" onPress={() => setCount(count + 1)} />
    </View>
  );
}
```

## useEffect Hook

```javascript
import { useEffect, useState } from 'react';

function DataFetcher() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('https://api.example.com/data')
      .then(r => r.json())
      .then(setData);
  }, []); // empty array = run once on mount
}
```

## Context API

For global state, React Native uses the same Context API as React:

```javascript
const ThemeContext = React.createContext('light');

function App() {
  return (
    <ThemeContext.Provider value="dark">
      <MyComponent />
    </ThemeContext.Provider>
  );
}
```

## Redux / Zustand

For complex state, Redux or Zustand are commonly used with React Native, following the same patterns as web React applications.

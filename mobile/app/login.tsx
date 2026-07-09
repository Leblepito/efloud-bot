import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { api } from '../src/api/client';
import { AuthContext } from './_layout';

/**
 * Login screen with Bearer token authentication.
 * User enters password, gets JWT-like token, stored in SecureStore.
 */
export default function LoginScreen() {
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();
  const { login } = React.useContext(AuthContext);

  const handleLogin = async () => {
    if (!password.trim()) {
      setError('Password cannot be empty');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      // Call mobile login endpoint
      const response = await api.post('/mobile/login', { password: password });

      if (response.data.ok && response.data.token) {
        // Store token and navigate to tabs
        await login(response.data.token);
        router.replace('/(tabs)');
      } else {
        setError('Login failed - no token received');
      }
    } catch (err: any) {
      // Handle various error scenarios
      if (err.response?.status === 401) {
        setError('Invalid password');
      } else if (err.response?.status === 429) {
        setError('Too many login attempts. Please try again later.');
      } else if (err.code === 'ECONNREFUSED') {
        setError('Cannot connect to server. Check your network connection.');
      } else {
        setError('Login failed. Please try again.');
        console.error('Login error:', err);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Efloud Bot Mobile</Text>
        <Text style={styles.subtitle}>Secure Trading Control</Text>

        <View style={styles.form}>
          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            placeholder="Enter dashboard password"
            secureTextEntry
            autoFocus
            editable={!isLoading}
            onSubmitEditing={handleLogin}
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Button
            title={isLoading ? 'Logging in...' : 'Login'}
            onPress={handleLogin}
            disabled={isLoading || !password.trim()}
          />

          <Text style={styles.help}>
            Enter your dashboard password to access trading controls and content approval.
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  card: {
    backgroundColor: 'white',
    borderRadius: 10,
    padding: 20,
    width: '100%',
    maxWidth: 400,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 5,
    color: '#333',
  },
  subtitle: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 30,
    color: '#666',
  },
  form: {
    gap: 15,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 5,
    padding: 12,
    fontSize: 16,
    backgroundColor: '#fafafa',
  },
  error: {
    color: '#ef4444',
    fontSize: 12,
    textAlign: 'center',
  },
  help: {
    fontSize: 12,
    textAlign: 'center',
    color: '#666',
    marginTop: 10,
    lineHeight: 16,
  },
});
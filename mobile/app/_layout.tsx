import { useEffect, useState } from 'react';
import { useRouter, useSegments } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import { View, ActivityIndicator } from 'react-native';

// Auth context to manage authentication state across the app
interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = React.createContext<AuthContextType>({
  isAuthenticated: false,
  isLoading: true,
  login: async () => {},
  logout: async () => {},
});

/**
 * Root layout with authentication control.
 * Checks for stored Bearer token and redirects to login if not authenticated.
 */
export default function RootLayout() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Check authentication status on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const token = await SecureStore.getItemAsync('mobile_token');
      setIsAuthenticated(!!token);
    } catch (error) {
      console.error('Error checking auth status:', error);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (token: string) => {
    await SecureStore.setItemAsync('mobile_token', token);
    setIsAuthenticated(true);
  };

  const logout = async () => {
    await SecureStore.deleteItemAsync('mobile_token');
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, login, logout }}>
      <AuthGate />
    </AuthContext.Provider>
  );
}

/**
 * Navigation gate - redirects to login if not authenticated.
 * Uses Expo Router's useSegments and useRouter for navigation control.
 */
function AuthGate() {
  const { isAuthenticated, isLoading } = React.useContext(AuthContext);
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    // Wait for auth check to complete
    if (isLoading) return;

    // Get current route segment
    const inAuthGroup = segments[0] === '(tabs)';

    // Redirect logic
    if (!isAuthenticated && !inAuthGroup) {
      // Not authenticated and not in auth group -> redirect to login
      router.replace('/login');
    } else if (isAuthenticated && inAuthGroup) {
      // Authenticated and trying to access auth-only routes -> redirect to tabs
      router.replace('/(tabs)');
    }
  }, [isAuthenticated, isLoading, segments]);

  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return <>{/* Expo Router will handle the rest */}</>;
}

// Import React at the top since we use it
import React from 'react';
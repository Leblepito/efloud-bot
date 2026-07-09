import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, RefreshControl, ActivityIndicator } from 'react-native';
import { getBotStatus } from '../../src/api/actions';

/**
 * Dashboard screen - shows bot status and health information.
 * Displays runtime status, uptime, positions count, last signal time.
 */
export default function DashboardScreen() {
  const [status, setStatus] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState('');

  const fetchStatus = async () => {
    try {
      setError('');
      const data = await getBotStatus();
      setStatus(data);
    } catch (err: any) {
      setError('Failed to load bot status');
      console.error('Status fetch error:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const onRefresh = () => {
    setIsRefreshing(true);
    fetchStatus();
  };

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case 'trading':
        return '#10b981'; // green
      case 'stopped':
      case 'idle':
        return '#f59e0b'; // orange
      case 'error':
      case 'halted':
        return '#ef4444'; // red
      default:
        return '#6b7280'; // gray
    }
  };

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" />
        <Text style={styles.loadingText}>Loading bot status...</Text>
      </View>
    );
  }

  if (error && !status) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />
      }
    >
      <View style={styles.header}>
        <Text style={styles.title}>Bot Status</Text>
        <Text style={styles.subtitle}>Real-time trading overview</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Runtime Status</Text>
        <View style={styles.statusRow}>
          <View style={[styles.statusIndicator, { backgroundColor: getStatusColor(status?.status || 'unknown') }]} />
          <Text style={styles.statusText}>{status?.status || 'Unknown'}</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Uptime</Text>
        <Text style={styles.value}>{status?.uptime_seconds ? formatUptime(status.uptime_seconds) : 'Unknown'}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Open Positions</Text>
        <Text style={styles.value}>{status?.positions ?? 0}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Last Signal</Text>
        <Text style={styles.value}>{formatDate(status?.last_signal_time)}</Text>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>
          Efloud Trading Bot v2.2.0
        </Text>
        <Text style={styles.footerText}>
          SMC Smart Money Concepts + Multi-Timeframe Analysis
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  header: {
    padding: 20,
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#111827',
  },
  subtitle: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 4,
  },
  card: {
    backgroundColor: 'white',
    margin: 16,
    marginTop: 0,
    padding: 16,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  cardTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusIndicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  statusText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#111827',
  },
  value: {
    fontSize: 18,
    fontWeight: '600',
    color: '#111827',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#6b7280',
  },
  errorText: {
    fontSize: 16,
    color: '#ef4444',
    textAlign: 'center',
  },
  footer: {
    padding: 24,
    alignItems: 'center',
    backgroundColor: 'white',
    marginTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  footerText: {
    fontSize: 12,
    color: '#9ca3af',
    textAlign: 'center',
    marginBottom: 4,
  },
});
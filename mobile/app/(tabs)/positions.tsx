import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { getPositions, closePosition } from '../../src/api/actions';
import { Position } from '../../src/api/client';

/**
 * Positions screen with biometric authentication for closing positions.
 * Lists all open positions with close buttons that require FaceID/TouchID confirmation.
 */
export default function PositionsScreen() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [closingPositions, setClosingPositions] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');

  const fetchPositions = async () => {
    try {
      setError('');
      const data = await getPositions();
      setPositions(data);
    } catch (err: any) {
      setError('Failed to load positions');
      console.error('Positions fetch error:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchPositions();
  }, []);

  const onRefresh = () => {
    setIsRefreshing(true);
    fetchPositions();
  };

  const handleClose = async (symbol: string, direction: 'LONG' | 'SHORT') => {
    const positionKey = `${symbol}-${direction}`;

    // Prevent double-tap
    if (closingPositions.has(positionKey)) {
      return;
    }

    Alert.alert(
      'Close Position',
      `Close ${direction} ${symbol} position?\n\nThis action requires biometric authentication.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Close',
          style: 'destructive',
          onPress: async () => {
            try {
              setClosingPositions(prev => new Set(prev).add(positionKey));

              // Call closePosition - this will trigger biometric auth internally
              const result = await closePosition(symbol, direction);

              if (result.ok) {
                Alert.alert(
                  'Success',
                  `Position closed: ${symbol} ${direction}`,
                  [{ text: 'OK', onPress: () => fetchPositions() }]
                );
              } else if (result.dedup) {
                Alert.alert('Duplicate', 'This close request was already processed');
              } else {
                Alert.alert('Failed', `Could not close position: ${symbol}`);
              }
            } catch (err: any) {
              // Biometric auth failed or other error
              const errorMessage = err.message || 'Failed to close position';
              Alert.alert('Error', errorMessage);
            } finally {
              setClosingPositions(prev => {
                const newSet = new Set(prev);
                newSet.delete(positionKey);
                return newSet;
              });
            }
          },
        },
      ]
    );
  };

  const renderPosition = (position: Position) => {
    const positionKey = `${position.symbol}-${position.direction}`;
    const isClosing = closingPositions.has(positionKey);
    const isProfitable = position.pnl_usd >= 0;

    return (
      <View key={positionKey} style={styles.positionCard}>
        <View style={styles.positionHeader}>
          <Text style={styles.symbol}>{position.symbol}</Text>
          <View style={[
            styles.directionBadge,
            { backgroundColor: position.direction === 'LONG' ? '#10b981' : '#ef4444' }
          ]}>
            <Text style={styles.directionText}>{position.direction}</Text>
          </View>
        </View>

        <View style={styles.positionDetails}>
          <View style={styles.detailRow}>
            <Text style={styles.label}>Entry:</Text>
            <Text style={styles.value}>${position.entry_price?.toFixed(2) || 'N/A'}</Text>
          </View>

          <View style={styles.detailRow}>
            <Text style={styles.label}>Current:</Text>
            <Text style={styles.value}>${position.current_price?.toFixed(2) || 'N/A'}</Text>
          </View>

          <View style={styles.detailRow}>
            <Text style={styles.label}>Size:</Text>
            <Text style={styles.value}>{position.size?.toFixed(4) || 'N/A'}</Text>
          </View>

          <View style={[styles.pnlRow, { borderColor: isProfitable ? '#10b981' : '#ef4444' }]}>
            <Text style={styles.label}>PnL:</Text>
            <Text style={[
              styles.pnlValue,
              { color: isProfitable ? '#10b981' : '#ef4444' }
            ]}>
              {isProfitable ? '+' : ''}{position.pnl_usd?.toFixed(2) || 'N/A'} USD
              ({isProfitable ? '+' : ''}{position.pnl_percent?.toFixed(2) || 'N/A'}%)
            </Text>
          </View>

          <Text style={styles.entryTime}>
            Entry: {new Date(position.entry_time).toLocaleString()}
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.closeButton, isClosing && styles.closeButtonDisabled]}
          onPress={() => handleClose(position.symbol, position.direction)}
          disabled={isClosing}
        >
          <Text style={styles.closeButtonText}>
            {isClosing ? 'Authenticating...' : 'Close Position'}
          </Text>
        </TouchableOpacity>
      </View>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" />
        <Text style={styles.loadingText}>Loading positions...</Text>
      </View>
    );
  }

  if (error && positions.length === 0) {
    return (
      <ScrollView
        style={styles.container}
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />
        }
      >
        <View style={styles.centerContainer}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      </ScrollView>
    );
  }

  if (positions.length === 0) {
    return (
      <ScrollView
        style={styles.container}
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />
        }
      >
        <View style={styles.centerContainer}>
          <Text style={styles.emptyText}>No open positions</Text>
          <Text style={styles.emptySubtext}>Pull to refresh</Text>
        </View>
      </ScrollView>
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
        <Text style={styles.title}>Open Positions ({positions.length})</Text>
        <Text style={styles.subtitle}>Biometric authentication required</Text>
      </View>

      {positions.map(renderPosition)}
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
    padding: 16,
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#111827',
  },
  subtitle: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 4,
  },
  positionCard: {
    backgroundColor: 'white',
    margin: 16,
    marginTop: 0,
    marginBottom: 12,
    padding: 16,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  positionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  symbol: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#111827',
  },
  directionBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  directionText: {
    fontSize: 12,
    fontWeight: '600',
    color: 'white',
  },
  positionDetails: {
    marginBottom: 16,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  label: {
    fontSize: 14,
    color: '#6b7280',
  },
  value: {
    fontSize: 14,
    fontWeight: '500',
    color: '#111827',
  },
  pnlRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    marginTop: 8,
    borderTopWidth: 1,
  },
  pnlValue: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  entryTime: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 8,
  },
  closeButton: {
    backgroundColor: '#ef4444',
    paddingVertical: 12,
    borderRadius: 6,
    alignItems: 'center',
  },
  closeButtonDisabled: {
    backgroundColor: '#9ca3af',
  },
  closeButtonText: {
    color: 'white',
    fontSize: 14,
    fontWeight: '600',
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
  emptyText: {
    fontSize: 18,
    color: '#6b7280',
    marginBottom: 4,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#9ca3af',
  },
});
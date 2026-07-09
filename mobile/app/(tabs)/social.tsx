import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Alert,
  Modal,
  TouchableOpacity,
  TextInput,
} from 'react-native';
import { getPendingDrafts, approveDraft, rejectDraft } from '../../src/api/actions';
import { ContentDraft } from '../../src/api/client';

/**
 * Social approval screen with biometric authentication for content approval.
 * Shows pending TR/EN drafts, allows editing and approval/rejection with FaceID/TouchID.
 */
export default function SocialScreen() {
  const [drafts, setDrafts] = useState<ContentDraft[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [processingDrafts, setProcessingDrafts] = useState<Set<string>>(new Set());
  const [selectedDraft, setSelectedDraft] = useState<ContentDraft | null>(null);
  const [editedBody, setEditedBody] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [error, setError] = useState('');

  const fetchDrafts = async () => {
    try {
      setError('');
      const data = await getPendingDrafts();
      setDrafts(data);
    } catch (err: any) {
      setError('Failed to load pending drafts');
      console.error('Drafts fetch error:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDrafts();
  }, []);

  const onRefresh = () => {
    setIsRefreshing(true);
    fetchDrafts();
  };

  const handleApprove = async (draft: ContentDraft) => {
    const draftKey = draft.draft_id;

    // Prevent double-tap
    if (processingDrafts.has(draftKey)) {
      return;
    }

    Alert.alert(
      'Approve Content',
      `Approve ${draft.lang} ${draft.post_type} for publishing?\n\nThis action requires biometric authentication.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Approve',
          style: 'default',
          onPress: async () => {
            try {
              setProcessingDrafts(prev => new Set(prev).add(draftKey));

              // Call approveDraft - this will trigger biometric auth internally
              const result = await approveDraft(draft.draft_id);

              if (result.ok) {
                Alert.alert(
                  'Success',
                  'Content approved for publishing',
                  [{ text: 'OK', onPress: () => {
                    setDrafts(prev => prev.filter(d => d.draft_id !== draft.draft_id));
                  }}]
                );
              } else {
                Alert.alert('Failed', 'Could not approve content');
              }
            } catch (err: any) {
              // Biometric auth failed or other error
              const errorMessage = err.message || 'Failed to approve content';
              Alert.alert('Error', errorMessage);
            } finally {
              setProcessingDrafts(prev => {
                const newSet = new Set(prev);
                newSet.delete(draftKey);
                return newSet;
              });
            }
          },
        },
      ]
    );
  };

  const handleReject = (draft: ContentDraft) => {
    setSelectedDraft(draft);
    setRejectionReason('');
    setShowRejectModal(true);
  };

  const confirmReject = async () => {
    if (!selectedDraft) return;

    const draftKey = selectedDraft.draft_id;

    try {
      setProcessingDrafts(prev => new Set(prev).add(draftKey));

      // Reject with reason (no biometric required for rejection)
      const result = await rejectDraft(selectedDraft.draft_id, rejectionReason);

      if (result.ok) {
        Alert.alert('Rejected', 'Content rejected successfully', [
          { text: 'OK', onPress: () => {
            setDrafts(prev => prev.filter(d => d.draft_id !== draftKey));
            setShowRejectModal(false);
            setSelectedDraft(null);
          }}
        ]);
      } else {
        Alert.alert('Failed', 'Could not reject content');
      }
    } catch (err: any) {
      Alert.alert('Error', 'Failed to reject content');
    } finally {
      setProcessingDrafts(prev => {
        const newSet = new Set(prev);
        newSet.delete(draftKey);
        return newSet;
      });
    }
  };

  const handleEdit = (draft: ContentDraft) => {
    setSelectedDraft(draft);
    setEditedBody(draft.body);
  };

  const saveEdit = () => {
    if (selectedDraft) {
      setDrafts(prev => prev.map(d =>
        d.draft_id === selectedDraft.draft_id
          ? { ...d, body: editedBody }
          : d
      ));
      setSelectedDraft(null);
      setEditedBody('');
    }
  };

  const getLanguageColor = (lang: string) => {
    switch (lang.toLowerCase()) {
      case 'tr':
        return '#ef4444'; // red for Turkish flag
      case 'en':
        return '#3b82f6'; // blue for English/US
      default:
        return '#6b7280'; // gray for others
    }
  };

  const getPostTypeIcon = (postType: string) => {
    switch (postType) {
      case 'signal':
        return '📊';
      case 'educational':
        return '📚';
      case 'performance_recap':
        return '📈';
      case 'promo':
        return '🎯';
      case 'market_update':
        return '📰';
      default:
        return '📝';
    }
  };

  const renderDraft = (draft: ContentDraft) => {
    const draftKey = draft.draft_id;
    const isProcessing = processingDrafts.has(draftKey);

    return (
      <View key={draftKey} style={styles.draftCard}>
        <View style={styles.draftHeader}>
          <View style={styles.draftMeta}>
            <View style={[
              styles.langBadge,
              { backgroundColor: getLanguageColor(draft.lang) }
            ]}>
              <Text style={styles.langText}>{draft.lang.toUpperCase()}</Text>
            </View>
            <Text style={styles.draftType}>
              {getPostTypeIcon(draft.post_type)} {draft.post_type}
            </Text>
          </View>
          <Text style={styles.draftTime}>
            {new Date(draft.created_at).toLocaleString()}
          </Text>
        </View>

        <Text style={styles.draftBody}>{draft.body}</Text>

        <View style={styles.draftActions}>
          <TouchableOpacity
            style={[styles.actionButton, styles.approveButton]}
            onPress={() => handleApprove(draft)}
            disabled={isProcessing}
          >
            <Text style={styles.actionButtonText}>
              {isProcessing ? 'Authenticating...' : 'Approve'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionButton, styles.editButton]}
            onPress={() => handleEdit(draft)}
          >
            <Text style={styles.actionButtonText}>Edit</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionButton, styles.rejectButton]}
            onPress={() => handleReject(draft)}
            disabled={isProcessing}
          >
            <Text style={styles.actionButtonText}>Reject</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" />
        <Text style={styles.loadingText}>Loading pending drafts...</Text>
      </View>
    );
  }

  if (error && drafts.length === 0) {
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

  if (drafts.length === 0) {
    return (
      <ScrollView
        style={styles.container}
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />
        }
      >
        <View style={styles.centerContainer}>
          <Text style={styles.emptyText}>No pending drafts</Text>
          <Text style={styles.emptySubtext}>Pull to refresh</Text>
        </View>
      </ScrollView>
    );
  }

  return (
    <View style={styles.container}>
      <Modal
        visible={showRejectModal}
        transparent
        animationType="slide"
      >
        <View style={styles.modalContainer}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Reject Content</Text>
            <Text style={styles.modalSubtitle}>
              Please provide a reason for rejection
            </Text>

            <TextInput
              style={styles.rejectInput}
              placeholder="Enter rejection reason..."
              value={rejectionReason}
              onChangeText={setRejectionReason}
              multiline
              numberOfLines={4}
              autoFocus
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalButton, styles.cancelModalButton]}
                onPress={() => {
                  setShowRejectModal(false);
                  setRejectionReason('');
                  setSelectedDraft(null);
                }}
              >
                <Text style={styles.modalButtonText}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.modalButton, styles.confirmModalButton]}
                onPress={confirmReject}
                disabled={!rejectionReason.trim()}
              >
                <Text style={styles.modalButtonText}>Reject</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <ScrollView
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh}
        }
      >
        <View style={styles.header}>
          <Text style={styles.title}>Pending Approval ({drafts.length})</Text>
          <Text style={styles.subtitle}>Biometric authentication required</Text>
        </View>

        {drafts.map(renderDraft)}
      </ScrollView>
    </View>
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
  draftCard: {
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
  draftHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  draftMeta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  langBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    marginRight: 8,
  },
  langText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: 'white',
  },
  draftType: {
    fontSize: 14,
    color: '#374151',
  },
  draftTime: {
    fontSize: 12,
    color: '#9ca3af',
  },
  draftBody: {
    fontSize: 14,
    lineHeight: 20,
    color: '#1f2937',
    marginBottom: 16,
  },
  draftActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  actionButton: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 6,
    alignItems: 'center',
    marginHorizontal: 4,
  },
  actionButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: 'white',
  },
  approveButton: {
    backgroundColor: '#10b981',
  },
  editButton: {
    backgroundColor: '#3b82f6',
  },
  rejectButton: {
    backgroundColor: '#ef4444',
  },
  modalContainer: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    backgroundColor: 'white',
    margin: 20,
    padding: 20,
    borderRadius: 10,
    width: '100%',
    maxWidth: 400,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  modalSubtitle: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 16,
  },
  rejectInput: {
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 6,
    padding: 12,
    minHeight: 80,
    textAlignVertical: 'top',
    marginBottom: 16,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  modalButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 6,
    alignItems: 'center',
    marginHorizontal: 8,
  },
  modalButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: 'white',
  },
  cancelModalButton: {
    backgroundColor: '#6b7280',
  },
  confirmModalButton: {
    backgroundColor: '#ef4444',
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
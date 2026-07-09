import 'react-native-get-random-values'; // Must import before uuid
import { v4 as uuidv4 } from 'uuid';
import { api, ClosePositionResponse, SocialApprovalResponse } from './client';
import { authenticateAction } from '../utils/auth';

/**
 * Close a trading position with biometric authentication.
 * Uses idempotency key to prevent duplicate close orders.
 *
 * @param symbol - Trading pair symbol (e.g., "BTCUSDT")
 * @param direction - Position direction ("LONG" or "SHORT")
 * @returns Promise with close result
 */
export async function closePosition(
  symbol: string,
  direction: 'LONG' | 'SHORT'
): Promise<ClosePositionResponse> {
  // CRITICAL: Require biometric authentication for order control
  const authOk = await authenticateAction(`${symbol} ${direction} pozisyonu kapat`);
  if (!authOk) {
    throw new Error('Biyometrik onay reddedildi');
  }

  // Generate unique idempotency key for this close attempt
  // This prevents duplicate orders if the user retries
  const idempotency_key = uuidv4();

  try {
    const response = await api.post<ClosePositionResponse>('/orders/close', {
      symbol,
      direction,
      idempotency_key,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to close position:', error);
    throw error;
  }
}

/**
 * Approve a content draft for publishing.
 * Requires biometric authentication as safety check for content publishing.
 *
 * @param draftId - Content draft identifier
 * @returns Promise with approval result
 */
export async function approveDraft(draftId: string): Promise<SocialApprovalResponse> {
  // CRITICAL: Require biometric authentication for content approval
  const authOk = await authenticateAction('İçeriği onayla ve yayına gönder');
  if (!authOk) {
    throw new Error('Onay reddedildi');
  }

  try {
    const response = await api.post<SocialApprovalResponse>('/social/approve', {
      draft_id: draftId,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to approve draft:', error);
    throw error;
  }
}

/**
 * Reject a content draft with reason.
 * No biometric required for rejection (safe action).
 *
 * @param draftId - Content draft identifier
 * @param reason - Rejection reason
 * @returns Promise with rejection result
 */
export async function rejectDraft(
  draftId: string,
  reason: string
): Promise<SocialApprovalResponse> {
  try {
    const response = await api.post<SocialApprovalResponse>('/social/reject', {
      draft_id: draftId,
      reason,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to reject draft:', error);
    throw error;
  }
}

/**
 * Get bot status and health information.
 * No authentication required (public endpoint).
 */
export async function getBotStatus() {
  try {
    const response = await api.get('/status');
    return response.data;
  } catch (error) {
    console.error('Failed to get bot status:', error);
    throw error;
  }
}

/**
 * Get current open positions.
 * Requires authentication.
 */
export async function getPositions() {
  try {
    const response = await api.get('/positions');
    return response.data;
  } catch (error) {
    console.error('Failed to get positions:', error);
    throw error;
  }
}

/**
 * Get pending content drafts awaiting approval.
 * Requires authentication.
 */
export async function getPendingDrafts() {
  try {
    const response = await api.get('/social/pending');
    return response.data;
  } catch (error) {
    console.error('Failed to get pending drafts:', error);
    throw error;
  }
}
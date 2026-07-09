import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

// Prod'da EAS env / app.config ile ver. localhost mobilden erişilemez —
// fiziksel cihaz test için LAN IP (http://192.168.x.x:8000), prod HTTPS URL.
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: Add Bearer token
api.interceptors.request.use(
  async (config) => {
    const token = await SecureStore.getItemAsync('mobile_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token expired - clear and redirect to login
      await SecureStore.deleteItemAsync('mobile_token');
      // In a real app, you'd navigate to login here
      console.log('Token expired, please login again');
    }
    return Promise.reject(error);
  }
);

// API response types
export interface BotStatus {
  status: string;
  uptime_seconds: number;
  positions: number;
  last_signal_time: string | null;
}

export interface Position {
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entry_price: number;
  current_price: number;
  size: number;
  pnl_usd: number;
  pnl_percent: number;
  entry_time: string;
}

export interface ContentDraft {
  draft_id: string;
  body: string;
  lang: string;
  post_type: string;
  meta: Record<string, any>;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  rejection_reason: string | null;
}

export interface ClosePositionResponse {
  ok: boolean;
  type: 'tracked' | 'untracked';
  dedup?: boolean;
}

export interface SocialApprovalResponse {
  ok: boolean;
  status: string;
}

export interface ErrorResponse {
  detail: string;
}
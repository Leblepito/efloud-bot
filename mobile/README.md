# Efloud Mobile App

Official mobile app for Efloud Trading Bot - secure position control and content approval on the go.

## Features

- **Secure Authentication**: Bearer token-based auth with biometric protection
- **Trading Control**: View and close positions with FaceID/TouchID confirmation
- **Content Approval**: Review and approve/reject social media content (TR/EN)
- **Real-time Status**: Bot dashboard with live status and health monitoring
- **Biometric Security**: Critical actions require device biometrics or passcode

## Tech Stack

- **Expo SDK 51**: Cross-platform mobile development
- **React Native 0.74**: Native UI components
- **TypeScript**: Type-safe development
- **Expo Router**: File-based routing
- **Axios**: HTTP client with interceptors
- **expo-secure-store**: Secure token storage
- **expo-local-authentication**: Biometric authentication

## Security Features

### Biometric Authentication
- **Position Closing**: Requires FaceID/TouchID before closing any trading position
- **Content Approval**: Biometric confirmation required for approving content
- **Passcode Fallback**: If no biometrics enrolled, device passcode is required
- **No Bypass**: Critical actions cannot be performed without authentication

### API Security
- **Bearer Tokens**: JWT-like tokens stored securely in device keychain
- **Automatic Expiry**: Tokens expire after 30 days, requiring re-login
- **HTTPS**: Production uses encrypted connections
- **Rate Limiting**: Login attempts limited to prevent brute force

## Setup Instructions

### Development Setup

1. **Install Dependencies**
   ```bash
   cd mobile
   npm install
   ```

2. **Configure API URL**
   ```bash
   # For local development (requires LAN IP)
   EXPO_PUBLIC_API_URL=http://YOUR_COMPUTER_IP:8000/api

   # For production
   EXPO_PUBLIC_API_URL=https://bot.ualgotrade.com/api
   ```

3. **Start Development Server**
   ```bash
   npm start
   ```

4. **Run on Device**
   ```bash
   # iOS Simulator
   npm run ios

   # Android Emulator
   npm run android

   # Physical Device (scan QR code from Expo Dev Tools)
   npm start
   ```

### Production Build

#### Build for iOS
```bash
npm install -g eas-cli
eas login
eas build:configure
eas build --platform ios
```

#### Build for Android
```bash
eas build --platform android
```

## App Structure

```
mobile/
├── app/                      # Expo Router screens
│   ├── _layout.tsx           # Root layout with auth control
│   ├── login.tsx             # Login screen with Bearer token
│   └── (tabs)/               # Tab navigation screens
│       ├── _layout.tsx       # Tab navigation configuration
│       ├── index.tsx         # Dashboard screen
│       ├── positions.tsx     # Positions with biometric close
│       └── social.tsx         # Content approval screen
├── src/
│   ├── api/
│   │   ├── client.ts         # Axios client with auth interceptors
│   │   └── actions.ts        # API action functions
│   └── utils/
│       └── auth.ts           # Biometric authentication utilities
├── assets/                   # Images and icons
├── package.json             # Dependencies
├── app.json                 # Expo configuration
└── tsconfig.json           # TypeScript configuration
```

## API Integration

### Authentication Flow
1. User enters password → `POST /api/mobile/login`
2. Server returns Bearer token
3. Token stored in `expo-secure-store`
4. All subsequent requests include `Authorization: Bearer {token}` header
5. Token auto-removed on 401 responses

### Critical Action Flow
1. User taps "Close Position" or "Approve"
2. App triggers `expo-local-authentication`
3. User confirms with FaceID/TouchID/Passcode
4. On success → API call executed
5. On failure → Action cancelled

## Security Considerations

### Biometric Bypass Prevention
- **No Silent Auth**: Even if biometrics fail, passcode is required
- **No Fallback to Unsecured**: Cannot skip biometric/passcode on stolen devices
- **Hardware Check**: Device biometric capability checked on each action
- **Enrollment Check**: User must have biometrics or passcode enabled

### Order Control Safety
- **Idempotency**: Each close action generates unique UUID to prevent duplicates
- **Confirmation Dialog**: Double confirmation before critical actions
- **Audit Trail**: All actions logged in backend `state/mobile_actions.jsonl`
- **Rate Limiting**: Login attempts limited (5 attempts per 15 minutes)

### Data Protection
- **Token Storage**: Bearer tokens stored in device keychain (not AsyncStorage)
- **No Local Caching**: Sensitive data never cached locally
- **Auto-Cleanup**: Tokens removed on 401 or logout
- **Network Security**: HTTPS required in production

## Environment Variables

### Development
```bash
EXPO_PUBLIC_API_URL=http://localhost:8000/api  # Local development
```

### Production
```bash
EXPO_PUBLIC_API_URL=https://bot.ualgotrade.com/api  # Production API
```

## Biometric Permissions

### iOS (Info.plist)
- `NSFaceIDUsageDescription`: Face ID authentication required
- `NSBiometricTouchIDUsageDescription`: Touch ID authentication required

### Android (AndroidManifest.xml)
- `USE_BIOMETRIC`: Biometric hardware permission
- `USE_FINGERPRINT`: Fingerprint sensor permission

## Testing

### Manual Testing Checklist
- [ ] Login with correct password
- [ ] Login with incorrect password
- [ ] View bot status dashboard
- [ ] View positions list
- [ ] Close position with FaceID
- [ ] Close position with TouchID
- [ ] Close position biometric failure
- [ ] View pending drafts
- [ ] Approve content with FaceID
- [ ] Reject content without biometric
- [ ] Edit draft body text
- [ ] Refresh on all screens
- [ ] Handle network errors
- [ ] Handle token expiry (401)

### Biometric Testing
- Test on device with FaceID enabled
- Test on device with TouchID only
- Test on device with no biometrics (passcode fallback)
- Test with biometric failure (wrong fingerprint)
- Test with user cancellation

## Troubleshooting

### "Cannot connect to server"
- Check `EXPO_PUBLIC_API_URL` environment variable
- For physical devices, use LAN IP instead of localhost
- Verify backend is running and accessible

### "Biometric authentication failed"
- Check device has biometrics enabled in settings
- Verify user has enrolled fingerprints or face
- Try device passcode if biometrics unavailable

### "Token expired"
- Auto-redirect to login screen
- Login again with dashboard password
- Check token hasn't been revoked on backend

### Build failures
- Ensure EAS project is configured: `eas build:configure`
- Check Apple Developer account is active (iOS)
- Verify Google Play Console setup (Android)

## Deployment

### iOS App Store
1. Configure Apple Developer account ($99/year)
2. Set up App Store Connect listing
3. Submit build via EAS
4. Wait for Apple review (1-3 days)

### Android Play Store
1. Configure Google Play Console ($25 one-time)
2. Create store listing
3. Submit build via EAS
4. Wait for Google review (1-3 days)

## Performance

- **Startup Time**: <2 seconds to login screen
- **Auth Check**: <500ms for biometric verification
- **API Calls**: <1 second for most operations
- **Refresh**: Pull-to-refresh on all screens

## Future Enhancements

- **Push Notifications**: Alerts for new positions or draft approvals
- **Dark Mode**: System theme support
- **Offline Mode**: Cached data for offline viewing
- **Multi-Language**: App localization for TR/EN users
- **Advanced Charting**: TradingView integration for position analysis

## Support

For issues or questions:
- Backend: Check `efloud-bot` repository
- Mobile: Create issue in mobile app repository
- Security: Report security concerns immediately

## License

Proprietary - Efloud Trading Bot © 2026
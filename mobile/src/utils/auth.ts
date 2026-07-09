import * as LocalAuthentication from 'expo-local-authentication';

/**
 * Authenticate critical actions with biometrics or device passcode.
 * This prevents unauthorized trading positions or content approvals on stolen devices.
 *
 * @param prompt - Message to show during authentication
 * @returns Promise<boolean> - true if authenticated, false otherwise
 */
export async function authenticateAction(
  prompt: string = 'Kritik işlem onayı'
): Promise<boolean> {
  try {
    // Check if hardware is available
    const hasHardware = await LocalAuthentication.hasHardwareAsync();

    // Check if user has enrolled biometrics or passcode
    const isEnrolled = await LocalAuthentication.isEnrolledAsync();

    // SECURITY REQUIREMENT: If device doesn't support biometrics or user hasn't enrolled,
    // STILL require device passcode (disableDeviceFallback: false).
    // This bypass prevention is critical for order control and financial safety.
    // A stolen phone without biometric/passcode protection should NOT allow trading actions.

    const authResult = await LocalAuthentication.authenticateAsync({
      promptMessage: prompt,
      fallbackLabel: 'PIN Kullan',
      disableDeviceFallback: false, // Allow passcode as fallback (important!)
      cancelLabel: 'İptal',
    });

    return authResult.success;
  } catch (error) {
    // User cancelled or biometric failed
    console.log('Authentication failed or cancelled:', error);
    return false;
  }
}

/**
 * Check if biometric authentication is available and enrolled.
 * Useful for UI to show/hide biometric prompts.
 */
export async function checkBiometricAvailability(): Promise<{
  available: boolean;
  enrolled: boolean;
  biometricType: string;
}> {
  try {
    const hasHardware = await LocalAuthentication.hasHardwareAsync();
    const isEnrolled = await LocalAuthentication.isEnrolledAsync();

    // Get biometric type (Face ID, Touch ID, etc.)
    let biometricType = 'None';
    if (hasHardware && isEnrolled) {
      const supportedTypes = await LocalAuthentication.supportedAuthenticationTypesAsync();
      if (supportedTypes.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) {
        biometricType = 'Face ID';
      } else if (supportedTypes.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) {
        biometricType = 'Touch ID';
      } else if (supportedTypes.includes(LocalAuthentication.AuthenticationType.IRIS)) {
        biometricType = 'Iris';
      }
    }

    return {
      available: hasHardware,
      enrolled: isEnrolled,
      biometricType,
    };
  } catch (error) {
    console.error('Error checking biometric availability:', error);
    return {
      available: false,
      enrolled: false,
      biometricType: 'Error',
    };
  }
}
/**
 * GhostGrid Client Firebase Configuration & Auth State Helper.
 * If credentials are not yet configured, enables seamless Local Dev Operative Mode.
 */

// Replace these placeholders with your actual Firebase Web App credentials when ready
const firebaseConfig = {
  apiKey: "DEV_MODE_API_KEY",
  authDomain: "ghostgrid-proxy.firebaseapp.com",
  projectId: "ghostgrid-proxy",
  storageBucket: "ghostgrid-proxy.appspot.com",
  messagingSenderId: "1234567890",
  appId: "1:1234567890:web:abcdef123456"
};

let authInstance = null;
let isDevMockMode = false;

// Initialize Firebase client safely
try {
  if (typeof firebase !== "undefined" && firebaseConfig.apiKey !== "DEV_MODE_API_KEY") {
    firebase.initializeApp(firebaseConfig);
    authInstance = firebase.auth();
    console.log("[GhostGrid] Firebase Client initialized in production mode.");
  } else {
    isDevMockMode = true;
    console.log("[GhostGrid] Running in Dev Mock Mode (Guest Operative active).");
  }
} catch (err) {
  isDevMockMode = true;
  console.warn("[GhostGrid] Firebase init fallback to dev mode:", err.message);
}

/**
 * Returns current user's authorization token for GhostGrid API calls.
 */
async function getAuthToken() {
  if (isDevMockMode || !authInstance || !authInstance.currentUser) {
    return "Bearer dev_mock_token";
  }
  const token = await authInstance.currentUser.getIdToken();
  return `Bearer ${token}`;
}
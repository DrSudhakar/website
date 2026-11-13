/* ==========================================================================
   Backend addresses. Fill these in AFTER you deploy the Firebase functions
   (see GUIDE.md, Part 5). `firebase deploy` prints one URL per function.
   Leave them empty and the demo pages simply show "backend not configured".
   ========================================================================== */
window.SITE_CONFIG = {
  STATUS_URL: "",   // e.g. https://api-status-xxxxxxxx-el.a.run.app
  EMPATHY_URL: "",  // e.g. https://empathy-run-xxxxxxxx-el.a.run.app
  EEG_URL: "",      // e.g. https://eeg-analyze-xxxxxxxx-el.a.run.app
  ACCOUNT_URL: "",  // e.g. https://account-xxxxxxxx-el.a.run.app

  /* Sign-in (GUIDE.md, Part 5B). Copy these four values from
     Firebase console → Project settings → Your apps → Web app → "SDK setup and configuration".
     They are not secrets: every website that uses Firebase sign-in publishes them. */
  FIREBASE: {
    apiKey: "",
    authDomain: "",   // e.g. your-project-id.firebaseapp.com
    projectId: "",
    appId: "",
  },

  /* Where visitors pay for minutes. Put your UPI QR code image at assets/img/upi-qr.png. */
  PAYMENT: {
    UPI_ID: "",                       // e.g. yourname@okaxis — lets phone users tap "Pay with UPI app"
    PAYEE_NAME: "Sudhakar Mishra",
    QR_IMAGE: "assets/img/upi-qr.png",
  },
};

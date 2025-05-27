# Production Wallet Directory

Place your Oracle Cloud Database wallet files here for production deployment:

1. Download wallet from Oracle Cloud Console
2. Extract all files to this directory
3. Update .env.oracle with production settings
4. Set DEMO_MODE=false

Required files:
- cwallet.sso
- ewallet.p12
- keystore.jks
- ojdbc.properties
- sqlnet.ora
- tnsnames.ora
- truststore.jks

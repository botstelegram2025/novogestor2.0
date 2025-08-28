/**
 * Configuração específica do WhatsApp Baileys para Railway
 */

const isRailway = process.env.RAILWAY_ENVIRONMENT_NAME !== undefined;

const config = {
    // Railway Environment Detection
    isRailway,
    
    // Port Configuration
    port: process.env.PORT || process.env.WHATSAPP_PORT || 3001,
    
    // Railway Optimized Timeouts
    timeouts: {
        defaultQuery: isRailway ? 180000 : 60000,      // 3 min for Railway
        connect: isRailway ? 180000 : 60000,           // 3 min for Railway
        retryDelay: isRailway ? 5000 : 2000,           // 5s for Railway
        keepAlive: isRailway ? 30000 : 20000,          // 30s for Railway
        auth: isRailway ? 300000 : 60000,              // 5 min for Railway
    },
    
    // Connection Settings
    connection: {
        maxReconnectAttempts: isRailway ? 10 : 5,
        reconnectDelay: isRailway ? 10000 : 5000,      // 10s for Railway
        maxConcurrentConnections: isRailway ? 1 : 2,   // Lower for Railway
        qrTimeout: isRailway ? 180000 : 60000,         // 3 min for Railway
    },
    
    // File Storage
    storage: {
        sessionsDir: './sessions',
        backupDir: './sessions_backup',
        authDir: 'auth_info_baileys',
    },
    
    // Railway Specific Settings
    railway: {
        domain: process.env.RAILWAY_PUBLIC_DOMAIN || 'localhost',
        privateDomain: process.env.RAILWAY_PRIVATE_DOMAIN || 'localhost',
        region: process.env.RAILWAY_REGION || 'us-west1',
    },
    
    // Health Check Configuration
    healthCheck: {
        enabled: true,
        path: '/health',
        interval: 60000,  // 1 minute
    },
    
    // CORS Configuration
    cors: {
        origin: isRailway ? true : ['http://localhost:*'],
        credentials: true,
        methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        allowedHeaders: ['Content-Type', 'Authorization'],
    },
    
    // Logging
    logging: {
        level: isRailway ? 'info' : 'debug',
        console: true,
        file: false,  // Railway handles logging
    }
};

module.exports = config;
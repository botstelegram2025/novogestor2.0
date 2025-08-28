#!/usr/bin/env python3
"""
Script de inicialização para Railway
Gerencia tanto o bot Telegram quanto o servidor WhatsApp
"""
import os
import sys
import threading
import subprocess
import time
import signal
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('railway_starter')

class RailwayStarter:
    def __init__(self):
        self.processes = []
        self.running = True
        
    def start_whatsapp_server(self):
        """Start WhatsApp Baileys server"""
        try:
            logger.info("🚀 Starting WhatsApp Baileys server...")
            cmd = ["node", "whatsapp_baileys_multi.js"]
            
            env = os.environ.copy()
            env['NODE_ENV'] = 'production'
            env['PORT'] = str(os.getenv('WHATSAPP_PORT', 3001))
            
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.processes.append(('whatsapp', process))
            
            # Log output in separate thread
            def log_output():
                for line in process.stdout:
                    logger.info(f"[WhatsApp] {line.strip()}")
                    
            threading.Thread(target=log_output, daemon=True).start()
            
            return process
            
        except Exception as e:
            logger.error(f"❌ Failed to start WhatsApp server: {e}")
            return None
    
    def start_telegram_bot(self):
        """Start Telegram bot"""
        try:
            # Wait for WhatsApp server to be ready
            time.sleep(5)
            
            logger.info("🤖 Starting Telegram bot...")
            cmd = ["python", "main.py"]
            
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.processes.append(('telegram', process))
            
            # Log output in separate thread
            def log_output():
                for line in process.stdout:
                    logger.info(f"[Telegram] {line.strip()}")
                    
            threading.Thread(target=log_output, daemon=True).start()
            
            return process
            
        except Exception as e:
            logger.error(f"❌ Failed to start Telegram bot: {e}")
            return None
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"📴 Received signal {signum}, shutting down...")
        self.running = False
        self.shutdown()
        
    def shutdown(self):
        """Gracefully shutdown all processes"""
        logger.info("🛑 Shutting down services...")
        
        for name, process in self.processes:
            try:
                logger.info(f"⏹️ Stopping {name}...")
                process.terminate()
                process.wait(timeout=10)
                logger.info(f"✅ {name} stopped")
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ Force killing {name}...")
                process.kill()
            except Exception as e:
                logger.error(f"❌ Error stopping {name}: {e}")
        
        sys.exit(0)
    
    def monitor_processes(self):
        """Monitor and restart failed processes"""
        while self.running:
            for i, (name, process) in enumerate(self.processes):
                if process.poll() is not None:  # Process has terminated
                    logger.warning(f"⚠️ {name} process died, restarting...")
                    
                    if name == 'whatsapp':
                        new_process = self.start_whatsapp_server()
                    elif name == 'telegram':
                        new_process = self.start_telegram_bot()
                    
                    if new_process:
                        self.processes[i] = (name, new_process)
                        logger.info(f"✅ {name} restarted")
                    else:
                        logger.error(f"❌ Failed to restart {name}")
            
            time.sleep(10)  # Check every 10 seconds
    
    def run(self):
        """Main execution method"""
        logger.info("🌟 Starting Railway deployment...")
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        
        # Start services
        whatsapp_process = self.start_whatsapp_server()
        if not whatsapp_process:
            logger.error("❌ Failed to start WhatsApp server")
            return
            
        telegram_process = self.start_telegram_bot()
        if not telegram_process:
            logger.error("❌ Failed to start Telegram bot")
            return
        
        logger.info("🚀 All services started successfully!")
        
        # Start monitoring
        try:
            self.monitor_processes()
        except KeyboardInterrupt:
            logger.info("📴 Received keyboard interrupt")
            self.shutdown()

if __name__ == "__main__":
    starter = RailwayStarter()
    starter.run()
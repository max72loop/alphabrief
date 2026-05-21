/**
 * PM2 Ecosystem — AlphaBrief
 *
 * Déploiement VPS (95.217.239.25) :
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *   pm2 startup
 *
 * Logs :
 *   pm2 logs alphabrief
 *
 * Forcer un run immédiat :
 *   pm2 restart alphabrief
 */

module.exports = {
  apps: [
    {
      name: 'alphabrief',

      // Lance directement le module Python
      interpreter: 'none',
      script: 'python3',
      args: '-u -m core.scheduler_runner',   // -u = unbuffered (logs immédiats)

      // Répertoire de travail = racine du projet sur le VPS
      cwd: '/root/alphabrief',               // ← adapter si le chemin diffère

      // Cron : toutes les nuits à 2h00 (UTC)
      cron_restart: '0 2 * * *',

      // Ne pas redémarrer automatiquement après la fin du script
      autorestart: false,

      // Pas de watch de fichiers
      watch: false,

      // Variables d'environnement PM2 (fallback si .env absent)
      // Les vraies valeurs sont dans .env — ne pas les mettre ici
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: '/root/alphabrief',
        NODE_ENV: 'production',
      },

      // Logs PM2
      out_file: '/root/alphabrief/logs/scheduler.log',
      error_file: '/root/alphabrief/logs/scheduler_err.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',

      // Arrêt propre : laisse le ticker en cours se terminer
      kill_timeout: 120000,
    },
  ],
}

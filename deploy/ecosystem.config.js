module.exports = {
  apps: [
    {
      name: 'surebet',
      script: 'run.py',
      interpreter: '/opt/surebet/venv/bin/python',
      cwd: '/opt/surebet',
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      watch: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
}

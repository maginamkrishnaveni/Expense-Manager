from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'expenses'

    def ready(self):
        """
        Called once when Django finishes loading the app registry.
        Seeds default data into SQLite if tables are empty.
        """
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return

        try:
            from .seed import seed_default_data
            seed_default_data()
        except Exception as e:
            print(f"[ExpenseIQ] Warning during seed: {e}")

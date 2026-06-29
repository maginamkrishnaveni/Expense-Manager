from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'expenses'

    def ready(self):
        """
        Called once when Django finishes loading the app registry.
        Initializes all MongoDB collections, indexes, and seed data.
        """
        # Guard against double-execution during Django's auto-reloader
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return

        try:
            from .models import initialize_collections
            initialize_collections()
        except Exception as e:
            print(f"[ExpenseIQ] ⚠️  Could not initialize collections: {e}")
            print("[ExpenseIQ] Make sure MongoDB is running on the configured URI.")

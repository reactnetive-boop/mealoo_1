"""
Master seeder — runs all seeders in dependency order.
Run from project root:  python seeds/run_all.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(label, fn):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    try:
        fn()
    except Exception as e:
        print(f"  [FAILED] {label}: {e}")
        raise


if __name__ == "__main__":
    # ── Standalone (no FK deps) ────────────────────────────────────────────
    from seeds.admin_users_seeder import seed as seed_admins
    from seeds.serviceable_pincodes_seeder import seed as seed_pincodes
    from seeds.menu_categories_seeder import seed as seed_categories
    from seeds.subscription_plans_seeder import seed as seed_plans

    # ── Primary entities ──────────────────────────────────────────────────
    from seeds.providers_seeder import seed as seed_providers
    from seeds.users_seeder import seed as seed_users

    # ── Provider & user dependents ─────────────────────────────────────────
    from seeds.delivery_boys_seeder import seed as seed_delivery_boys
    from seeds.user_addresses_seeder import seed as seed_addresses
    from seeds.wallets_seeder import seed as seed_wallets
    from seeds.provider_wallets_seeder import seed as seed_provider_wallets

    # ── Menu content ──────────────────────────────────────────────────────
    from seeds.menu_packages_seeder import seed as seed_packages

    # ── Transactional data ────────────────────────────────────────────────
    from seeds.subscriptions_seeder import seed as seed_subscriptions
    from seeds.orders_seeder import seed as seed_orders
    from seeds.extra_orders_seeder import seed as seed_extra_orders
    from seeds.wallet_transactions_seeder import seed as seed_wallet_transactions

    # ── Social / activity data ────────────────────────────────────────────
    from seeds.reviews_seeder import seed as seed_reviews
    from seeds.complaints_seeder import seed as seed_complaints
    from seeds.provider_complaints_seeder import seed as seed_provider_complaints
    from seeds.notifications_seeder import seed as seed_notifications
    from seeds.cart_items_seeder import seed as seed_cart_items

    run("1/19 — Admin Users",            seed_admins)
    run("2/19 — Serviceable Pincodes",   seed_pincodes)
    run("3/19 — Menu Categories",        seed_categories)
    run("4/19 — Subscription Plans",     seed_plans)
    run("5/19 — Providers",              seed_providers)
    run("6/19 — Users",                  seed_users)
    run("7/19 — Delivery Boys",          seed_delivery_boys)
    run("8/19 — User Addresses",         seed_addresses)
    run("9/19 — User Wallets",           seed_wallets)
    run("10/19 — Provider Wallets",      seed_provider_wallets)
    run("11/19 — Menu Packages",         seed_packages)
    run("12/19 — Subscriptions",         seed_subscriptions)
    run("13/19 — Orders",                seed_orders)
    run("14/19 — Extra Orders",          seed_extra_orders)
    run("15/19 — Wallet Transactions",   seed_wallet_transactions)
    run("16/19 — Reviews",               seed_reviews)
    run("17/19 — Complaints",            seed_complaints)
    run("18/19 — Provider Complaints",   seed_provider_complaints)
    run("19/19 — Notifications",         seed_notifications)
    run("20/20 — Cart Items",            seed_cart_items)

    print(f"\n{'='*60}")
    print("  All seeders completed successfully!")
    print(f"{'='*60}\n")

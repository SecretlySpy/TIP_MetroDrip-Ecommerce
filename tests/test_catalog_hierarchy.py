"""Two-level category taxonomy: model rules, queries, navigation, and seeding.

Covers Epics A–C. Storefront rendering assertions that depend on the shop page
itself live in test_storefront.py; this module owns the hierarchy contract.
"""

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client

from apps.catalog.models import Category, Product, ProductVariant
from apps.catalog.seed_catalog import (
    AUDIENCES,
    allocate_round_robin,
    mock_product_slug,
    mock_sku,
)
from apps.catalog.services import get_catalog_queryset, get_category_tree
from apps.inventory.models import StockMovement, StockRecord

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def hoodies():
    return Category.objects.create(name="Hoodies", slug="hoodies")


@pytest.fixture()
def tees():
    return Category.objects.create(name="T-Shirts", slug="t-shirts")


@pytest.fixture()
def hoodies_men(hoodies):
    return Category.objects.create(name="Men", slug="hoodies-men", parent=hoodies)


@pytest.fixture()
def hoodies_women(hoodies):
    return Category.objects.create(name="Women", slug="hoodies-women", parent=hoodies)


def make_product(category, slug, *, name=None, active=True, price=99900):
    return Product.objects.create(
        name=name or slug.replace("-", " ").title(),
        slug=slug,
        category=category,
        base_price=price,
        is_active=active,
    )


# ---------------------------------------------------------------------------
# A-1: model rules
# ---------------------------------------------------------------------------


class TestCategoryHierarchyRules:
    def test_root_has_no_parent(self, hoodies):
        assert hoodies.is_root
        assert hoodies.hierarchy_label == "Hoodies"

    def test_child_reports_its_branch(self, hoodies_men):
        assert not hoodies_men.is_root
        assert hoodies_men.hierarchy_label == "Hoodies → Men"

    def test_same_child_name_allowed_under_different_parents(self, hoodies, tees):
        """ "Men" must exist under every main category — the whole point of FR-2."""
        Category.objects.create(name="Men", slug="hoodies-men", parent=hoodies)
        Category.objects.create(name="Men", slug="t-shirts-men", parent=tees)

        assert Category.objects.filter(name="Men").count() == 2

    def test_duplicate_sibling_name_rejected(self, hoodies, hoodies_men):
        duplicate = Category(name="Men", slug="hoodies-men-again", parent=hoodies)

        with pytest.raises(ValidationError) as exc:
            duplicate.full_clean()

        assert "name" in exc.value.error_dict

    def test_duplicate_root_name_rejected(self, hoodies):
        """MySQL cannot enforce this (NULL parents never collide), so clean() must."""
        duplicate = Category(name="Hoodies", slug="hoodies-2")

        with pytest.raises(ValidationError) as exc:
            duplicate.full_clean()

        assert "name" in exc.value.error_dict

    def test_third_level_rejected(self, hoodies_men):
        grandchild = Category(name="Petite", slug="hoodies-men-petite", parent=hoodies_men)

        with pytest.raises(ValidationError) as exc:
            grandchild.full_clean()

        assert "parent" in exc.value.error_dict

    def test_self_parenting_rejected(self, hoodies):
        hoodies.parent = hoodies

        with pytest.raises(ValidationError) as exc:
            hoodies.full_clean()

        assert "parent" in exc.value.error_dict

    def test_root_with_children_cannot_become_a_child(self, hoodies, tees, hoodies_men):
        hoodies.parent = tees

        with pytest.raises(ValidationError) as exc:
            hoodies.full_clean()

        assert "parent" in exc.value.error_dict

    def test_child_slugs_stay_globally_unique(self, hoodies, tees, hoodies_men):
        clash = Category(name="Men", slug="hoodies-men", parent=tees)

        with pytest.raises(ValidationError) as exc:
            clash.full_clean()

        assert "slug" in exc.value.error_dict

    def test_parent_is_protected_from_deletion(self, hoodies, hoodies_men):
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            hoodies.delete()


# ---------------------------------------------------------------------------
# A-2: migration outcome
# ---------------------------------------------------------------------------


class TestMigratedTaxonomy:
    def test_seed_demo_roots_gain_audience_children(self):
        """seed_demo predates the hierarchy, so the command back-fills children."""
        call_command("seed_demo")
        call_command("seed_mock_catalog", count=0)

        roots = Category.objects.filter(parent__isnull=True)
        assert roots.exists()

        for root in roots:
            names = set(root.children.values_list("name", flat=True))
            assert names == {audience["name"] for audience in AUDIENCES}
            for audience in AUDIENCES:
                slug = f"{root.slug}-{audience['slug_suffix']}"
                assert root.children.filter(slug=slug).exists()


# ---------------------------------------------------------------------------
# B-1: tree service
# ---------------------------------------------------------------------------


class TestCategoryTree:
    def test_tree_nests_children_under_roots(self, hoodies, hoodies_men, hoodies_women):
        tree = get_category_tree()

        assert [root.slug for root in tree] == ["hoodies"]
        assert [child.slug for child in tree[0].child_categories] == [
            "hoodies-men",
            "hoodies-women",
        ]

    def test_counts_only_include_active_products(self, hoodies, hoodies_men):
        make_product(hoodies_men, "live-one")
        make_product(hoodies_men, "hidden-one", active=False)

        tree = get_category_tree()

        assert tree[0].child_categories[0].product_count == 1

    def test_root_total_spans_direct_and_child_products(self, hoodies, hoodies_men, hoodies_women):
        make_product(hoodies, "legacy-direct")
        make_product(hoodies_men, "mens-one")
        make_product(hoodies_women, "womens-one")

        root = get_category_tree()[0]

        assert root.product_count == 1
        assert root.total_product_count == 3

    def test_tree_costs_two_queries(
        self, django_assert_num_queries, hoodies, tees, hoodies_men, hoodies_women
    ):
        """NFR-1: one query for roots, one for children — never per-category."""
        with django_assert_num_queries(2):
            tree = get_category_tree()
            for root in tree:
                list(root.child_categories)


# ---------------------------------------------------------------------------
# B-2: hierarchy-aware filtering
# ---------------------------------------------------------------------------


class TestHierarchicalFiltering:
    def test_root_slug_includes_direct_and_child_products(
        self, hoodies, hoodies_men, hoodies_women
    ):
        make_product(hoodies, "legacy-direct")
        make_product(hoodies_men, "mens-one")
        make_product(hoodies_women, "womens-one")

        results = get_catalog_queryset(filters={"category": "hoodies"})

        assert results.count() == 3

    def test_child_slug_returns_only_its_own_products(self, hoodies, hoodies_men, hoodies_women):
        make_product(hoodies, "legacy-direct")
        make_product(hoodies_men, "mens-one")
        make_product(hoodies_women, "womens-one")

        results = get_catalog_queryset(filters={"category": "hoodies-men"})

        assert [product.slug for product in results] == ["mens-one"]

    def test_sibling_branches_do_not_leak(self, hoodies, tees, hoodies_men):
        make_product(hoodies_men, "mens-hoodie")
        make_product(tees, "a-tee")

        assert get_catalog_queryset(filters={"category": "t-shirts"}).count() == 1
        assert get_catalog_queryset(filters={"category": "hoodies"}).count() == 1

    def test_unknown_slug_returns_nothing(self, hoodies_men):
        make_product(hoodies_men, "mens-one")

        assert get_catalog_queryset(filters={"category": "not-a-category"}).count() == 0

    def test_no_duplicate_rows_when_filtering(self, hoodies, hoodies_men):
        """The OR across two joins must not multiply rows."""
        make_product(hoodies_men, "mens-one")

        results = get_catalog_queryset(filters={"category": "hoodies"})

        assert results.count() == len({product.pk for product in results})


# ---------------------------------------------------------------------------
# B-3/B-4: deterministic placeholder seeding
# ---------------------------------------------------------------------------


class TestAllocateRoundRobin:
    def test_spreads_remainder_across_leading_buckets(self):
        assert allocate_round_robin(100, 18) == [6] * 10 + [5] * 8
        assert sum(allocate_round_robin(100, 18)) == 100

    def test_exact_division(self):
        assert allocate_round_robin(18, 18) == [1] * 18

    def test_no_buckets(self):
        assert allocate_round_robin(10, 0) == []


class TestSeedMockCatalog:
    def test_creates_requested_placeholders_across_every_leaf(self, hoodies, tees):
        call_command("seed_mock_catalog", count=20)

        assert Product.objects.filter(is_mock=True).count() == 20

        leaves = Category.objects.filter(parent__isnull=False)
        assert leaves.count() == 4
        for leaf in leaves:
            assert leaf.products.filter(is_mock=True).exists()

    def test_every_placeholder_gets_variant_stock_and_ledger(self, hoodies):
        call_command("seed_mock_catalog", count=4)

        for product in Product.objects.filter(is_mock=True):
            variant = product.variants.get()
            assert variant.sku.startswith("MD-MOCK-")
            assert StockRecord.objects.filter(variant=variant).exists()
            assert StockMovement.objects.filter(variant=variant).count() == 1

    def test_placeholders_are_active_and_flagged(self, hoodies):
        call_command("seed_mock_catalog", count=2)

        for product in Product.objects.filter(is_mock=True):
            assert product.is_active
            assert product.images == []
            assert product.base_price > 0

    def test_rerun_creates_nothing(self, hoodies, tees):
        call_command("seed_mock_catalog", count=10)
        before = {
            "products": Product.objects.count(),
            "variants": ProductVariant.objects.count(),
            "stock": StockRecord.objects.count(),
            "movements": StockMovement.objects.count(),
            "categories": Category.objects.count(),
        }

        call_command("seed_mock_catalog", count=10)

        assert Product.objects.count() == before["products"]
        assert ProductVariant.objects.count() == before["variants"]
        assert StockRecord.objects.count() == before["stock"]
        assert StockMovement.objects.count() == before["movements"]
        assert Category.objects.count() == before["categories"]

    def test_rerun_preserves_existing_stock(self, hoodies):
        call_command("seed_mock_catalog", count=2)
        record = StockRecord.objects.first()
        record.qty_on_hand = 3
        record.qty_reserved = 1
        record.low_stock_threshold = 99
        record.save()

        call_command("seed_mock_catalog", count=2)

        record.refresh_from_db()
        assert record.qty_on_hand == 3
        assert record.qty_reserved == 1
        assert record.low_stock_threshold == 99

    def test_rerun_restores_a_missing_stock_record(self, hoodies):
        """A placeholder whose inventory row vanished must become buyable again."""
        call_command("seed_mock_catalog", count=2)
        variant = ProductVariant.objects.first()
        StockRecord.objects.filter(variant=variant).delete()

        call_command("seed_mock_catalog", count=2)

        assert StockRecord.objects.filter(variant=variant).exists()
        assert Product.objects.filter(is_mock=True).count() == 2

    def test_healing_does_not_double_post_the_ledger(self, hoodies):
        """The surviving +25 must not be joined by a second one.

        StockMovement is append-only, so a duplicated opening balance could
        never be corrected — the ledger would disagree with qty_on_hand forever.
        """
        call_command("seed_mock_catalog", count=2)
        variant = ProductVariant.objects.first()
        StockRecord.objects.filter(variant=variant).delete()

        call_command("seed_mock_catalog", count=2)

        assert StockMovement.objects.filter(variant=variant).count() == 1

    def test_over_target_is_not_destructive(self, hoodies):
        call_command("seed_mock_catalog", count=10)

        call_command("seed_mock_catalog", count=4)

        assert Product.objects.filter(is_mock=True).count() == 10

    def test_does_not_touch_hand_authored_products(self, hoodies):
        real = make_product(hoodies, "real-product", name="Real Product")

        call_command("seed_mock_catalog", count=6)

        real.refresh_from_db()
        assert real.is_mock is False
        assert real.category == hoodies
        assert real.name == "Real Product"

    def test_dry_run_writes_nothing(self, hoodies):
        call_command("seed_mock_catalog", count=6, dry_run=True)

        assert Product.objects.count() == 0
        assert Category.objects.filter(parent__isnull=False).count() == 0

    def test_slugs_and_skus_match_their_natural_keys(self, hoodies):
        """Names derive purely from (category, audience, sequence).

        Asserted against the helpers rather than by re-seeding a wiped
        catalog: StockMovement is an append-only ledger that PROTECTs its
        variant, so generated products cannot be deleted — which is itself the
        reason idempotency has to come from natural keys instead of teardown.
        """
        call_command("seed_mock_catalog", count=2)

        expected_slugs = {
            mock_product_slug("hoodies", audience["slug_suffix"], 1) for audience in AUDIENCES
        }
        expected_skus = {mock_sku("hoodies", audience["code"], 1) for audience in AUDIENCES}

        assert set(Product.objects.filter(is_mock=True).values_list("slug", flat=True)) == (
            expected_slugs
        )
        assert set(ProductVariant.objects.values_list("sku", flat=True)) == expected_skus

    def test_refuses_when_no_root_categories_exist(self):
        call_command("seed_mock_catalog", count=5)

        assert Product.objects.count() == 0


# ---------------------------------------------------------------------------
# C-1/C-2: global navigation
# ---------------------------------------------------------------------------


class TestCategoryNavigation:
    def test_menu_renders_on_every_storefront_page(self, hoodies, hoodies_men):
        client = Client()

        for path in ("/", "/shop/", "/cart/"):
            body = client.get(path).content.decode()
            assert 'id="category-menu"' in body, path
            assert "Browse Categories" in body, path

    def test_menu_links_to_root_and_child_filters(self, hoodies, hoodies_men, hoodies_women):
        body = Client().get("/").content.decode()

        assert "/shop/?category=hoodies" in body
        assert "/shop/?category=hoodies-men" in body
        assert "/shop/?category=hoodies-women" in body

    def test_disclosure_is_keyboard_operable_without_javascript(self, hoodies, hoodies_men):
        """<details>/<summary> carries native semantics, so no ARIA is faked."""
        body = Client().get("/").content.decode()

        assert "<summary" in body
        assert 'aria-controls="category-menu"' in body

    def test_counts_render_in_the_menu(self, hoodies, hoodies_men):
        make_product(hoodies_men, "mens-one")

        body = Client().get("/").content.decode()

        assert "category-menu__count" in body

    def test_empty_taxonomy_does_not_break_pages(self):
        response = Client().get("/")

        assert response.status_code == 200

    def test_template_comments_never_reach_the_browser(self, hoodies, hoodies_men):
        """Django's {# #} comment is single-line only.

        A multi-line one is not a comment at all — it renders verbatim. Placed
        inside a tag it corrupts that tag's attributes, which is invisible to
        any assertion that merely greps the response for a substring.
        """
        client = Client()

        for path in ("/", "/shop/", "/cart/"):
            body = client.get(path).content.decode()
            assert "{#" not in body, path
            assert "#}" not in body, path
            assert "{% comment" not in body, path
            assert "{% endcomment" not in body, path

    def test_body_tag_is_well_formed(self, hoodies):
        """The disclosure handlers previously leaked into <body>'s attributes."""
        body = Client().get("/").content.decode()
        opening_tag = body[body.index("<body") : body.index(">", body.index("<body")) + 1]

        # Alpine's x-data="{ ... }" means plain braces are legitimate here;
        # only Django's own delimiters indicate an unrendered template block.
        assert "{#" not in opening_tag
        assert "{%" not in opening_tag
        assert opening_tag.count("<") == 1

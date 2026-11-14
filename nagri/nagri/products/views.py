from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Category, Product, ProductAttributeDefinition, SubCategory
from .serializers import CategorySerializer, ProductSerializer, SubCategorySerializer


def _get_cached_categories():
    cache_key = "nagri_categories"
    categories = cache.get(cache_key)
    if categories is None:
        categories = list(
            Category.objects.annotate(product_count=Count("products", distinct=True))
            .filter(products__is_active=True, products__review_status="approved")
            .order_by("name")
            .values("id", "name", "product_count")
        )
        cache.set(cache_key, categories, 600)
    return categories


def product_list_view(request):
    queryset = (
        Product.objects.select_related("category", "subcategory", "inventory")
        .prefetch_related(
            "images",
            "variants__inventory",
            "variants__measurement",
            "attribute_values__definition",
        )
        .filter(is_active=True, review_status="approved")
        .order_by("-is_featured", "-is_bestseller", "-rating", "-created_at", "id")
    )

    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "").strip()
    subcategory = request.GET.get("subcategory", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    freebies = request.GET.get("freebies", "").strip()

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(short_description__icontains=search)
            | Q(tags__icontains=search)
            | Q(brand__icontains=search)
        )

    if category:
        queryset = queryset.filter(Q(category_id=category) | Q(category__slug=category))

    if subcategory:
        queryset = queryset.filter(Q(subcategory_id=subcategory) | Q(subcategory__slug=subcategory))

    if min_price:
        try:
            queryset = queryset.filter(price__gte=min_price)
        except ValueError:
            pass

    if max_price:
        try:
            queryset = queryset.filter(price__lte=max_price)
        except ValueError:
            pass

    # Freebies filter: show products with price <= 0 or tagged as freebies via tags field
    if freebies:
        try:
            # If a numeric freebies parameter is passed (e.g. freebies=1), apply simple rule
            queryset = queryset.filter(Q(price__lte=0) | Q(tags__icontains='freebie') | Q(tags__icontains='freebies'))
        except Exception:
            pass

    paginator = Paginator(queryset, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "search": search,
        "category": category,
        "category_filter": category,
        "subcategory": subcategory,
        "min_price": min_price,
        "max_price": max_price,
        "categories": _get_cached_categories(),
    }
    return render(request, "products/product_list.html", context)


class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("id")
    serializer_class = CategorySerializer
    permission_classes = [IsStaffOrReadOnly]

    @action(detail=True, methods=["get"])
    def subcategories(self, request, pk=None):
        category = self.get_object()
        subcategories = SubCategory.objects.filter(category=category)
        serializer = SubCategorySerializer(subcategories, many=True)
        return Response(serializer.data)

    def perform_destroy(self, instance):
        if instance.products.filter(order_items__isnull=False).exists():
            raise PermissionDenied(
                "Cannot delete a category containing products referenced by orders."
            )
        super().perform_destroy(instance)


class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.select_related("category").all().order_by("id")
    serializer_class = SubCategorySerializer
    permission_classes = [IsStaffOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset


@require_GET
def product_attribute_definitions(request):
    category_id = request.GET.get("category")
    if not category_id or not category_id.isdecimal():
        return JsonResponse({"attributes": []})
    definitions = list(ProductAttributeDefinition.objects.filter(
        category_id=category_id,
        subcategory__isnull=True,
        is_active=True,
    ).order_by("sort_order", "id"))
    subcategory_id = request.GET.get("subcategory")
    if subcategory_id and subcategory_id.isdecimal():
        definitions.extend(ProductAttributeDefinition.objects.filter(
            category_id=category_id,
            subcategory_id=subcategory_id,
            is_active=True,
        ).order_by("sort_order", "id"))
    merged = {definition.key: definition for definition in definitions}
    return JsonResponse({
        "attributes": [
            {
                "key": item.key,
                "label": item.label,
                "data_type": item.data_type,
                "required": item.is_required,
                "options": item.options,
                "unit": item.unit,
            }
            for item in merged.values()
        ]
    })


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related(
        "category", "subcategory", "inventory", "measurement"
    ).prefetch_related(
        "images", "variants__inventory", "variants__measurement", "attribute_values__definition"
    ).all().order_by("id")
    serializer_class = ProductSerializer
    permission_classes = [IsStaffOrReadOnly]

    def get_queryset(self):
        queryset = Product.objects.select_related(
            "category", "subcategory", "inventory", "measurement"
        ).prefetch_related(
            "images", "variants__inventory", "variants__measurement", "attribute_values__definition"
        ).all()
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(is_active=True, review_status="approved")

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)

        subcategory = self.request.query_params.get("subcategory")
        if subcategory:
            queryset = queryset.filter(subcategory_id=subcategory)

        brand = self.request.query_params.get("brand")
        if brand:
            queryset = queryset.filter(brand__icontains=brand)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(short_description__icontains=search)
                | Q(tags__icontains=search)
            )

        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        in_stock = self.request.query_params.get("in_stock")
        if in_stock is not None:
            available_variant = Q(
                variants__is_active=True,
                variants__inventory__stock_quantity__gt=0,
            )
            available_simple = Q(
                variants__isnull=True,
                inventory__stock_quantity__gt=0,
            )
            queryset = (
                queryset.filter(available_variant | available_simple)
                if in_stock.lower() == "true"
                else queryset.exclude(available_variant | available_simple)
            )

        rating = self.request.query_params.get("rating")
        if rating:
            queryset = queryset.filter(rating__gte=rating)

        featured = self.request.query_params.get("featured")
        if featured is not None:
            queryset = queryset.filter(is_featured=featured.lower() == "true")

        bestseller = self.request.query_params.get("bestseller")
        if bestseller is not None:
            queryset = queryset.filter(is_bestseller=bestseller.lower() == "true")

        return queryset.order_by("-is_featured", "-is_bestseller", "-rating", "id")

    def perform_destroy(self, instance):
        if instance.order_items.exists():
            raise PermissionDenied(
                "Cannot delete a product referenced by order history."
            )
        super().perform_destroy(instance)

    @action(detail=False, methods=["get"])
    def featured(self, request):
        products = self.get_queryset().filter(is_featured=True)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def bestsellers(self, request):
        products = self.get_queryset().filter(is_bestseller=True)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)


def product_detail_view(request, product_id):
    """Display detailed information about a specific product"""
    from django.shortcuts import get_object_or_404

    product= get_object_or_404(
        Product.objects.select_related("category", "subcategory", "inventory", "measurement")
        .prefetch_related("images", "variants__inventory", "variants__measurement"),
        id=product_id,
        is_active=True,
        review_status="approved",
    )
    recently_viewed = [
        viewed_id for viewed_id in request.session.get("recently_viewed_products", [])
        if viewed_id != product.id
    ]
    request.session["recently_viewed_products"] = ([product.id] + recently_viewed)[:12]
    related_products = (
        Product.objects.select_related("category", "subcategory", "inventory")
        .prefetch_related("variants__inventory")
        .filter(category=product.category, is_active=True, review_status="approved")
        .exclude(id=product_id)
        .order_by("-rating", "-created_at")[:6]
    )

    context = {
        'product': product,
        'related_products': related_products,
        'variants': product.variants.filter(is_active=True).select_related("inventory", "measurement"),
        'measurement': getattr(product, "measurement", None),
        'attributes': product.attribute_values.select_related("definition").filter(
            definition__is_active=True
        ).order_by("definition__sort_order"),
    }
    if context["measurement"]:
        measurement = context["measurement"]
        context["measurement_values"] = {
            "length": measurement.dimension_in_display_unit(measurement.length_mm),
            "width": measurement.dimension_in_display_unit(measurement.width_mm),
            "height": measurement.dimension_in_display_unit(measurement.height_mm),
            "product_weight": measurement.weight_in_display_unit(measurement.product_weight_g),
            "packaging_weight": measurement.weight_in_display_unit(measurement.packaging_weight_g),
            "shipping_weight": measurement.weight_in_display_unit(measurement.shipping_weight_g),
        }
    return render(request, 'products/product_detail.html', context)

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Category, Product, SubCategory
from .serializers import CategorySerializer, ProductSerializer, SubCategorySerializer


def _get_cached_categories():
    cache_key = "nagri_categories"
    categories = cache.get(cache_key)
    if categories is None:
        categories = list(
            Category.objects.annotate(product_count=Count("products", distinct=True))
            .order_by("name")
            .values("id", "name", "product_count")
        )
        cache.set(cache_key, categories, 600)
    return categories


def product_list_view(request):
    queryset = (
        Product.objects.select_related("category", "subcategory", "inventory")
        .filter(is_active=True)
        .order_by("-is_featured", "-is_bestseller", "-rating", "-created_at", "id")
    )

    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "").strip()
    subcategory = request.GET.get("subcategory", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()

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


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("id")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["get"])
    def subcategories(self, request, pk=None):
        category = self.get_object()
        subcategories = SubCategory.objects.filter(category=category)
        serializer = SubCategorySerializer(subcategories, many=True)
        return Response(serializer.data)


class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.select_related("category").all().order_by("id")
    serializer_class = SubCategorySerializer
    permission_classes = [permissions.AllowAny]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category", "subcategory", "inventory").all().order_by("id")
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Product.objects.select_related("category", "subcategory", "inventory").all()

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
            queryset = queryset.filter(inventory__stock_quantity__gt=0) if in_stock.lower() == "true" else queryset.filter(inventory__stock_quantity__lte=0)

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
        Product.objects.select_related("category", "subcategory", "inventory"),
        id=product_id,
        is_active=True,
    )
    related_products = (
        Product.objects.select_related("category", "subcategory", "inventory")
        .filter(category=product.category, is_active=True)
        .exclude(id=product_id)
        .order_by("-rating", "-created_at")[:6]
    )

    context = {
        'product': product,
        'related_products': related_products,
    }
    return render(request, 'products/product_detail.html', context)

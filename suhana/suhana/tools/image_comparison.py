from .rust_engine import compare_image_pair, inspect_image


def image_metadata(data):
    return inspect_image(data)


def compare_image_pair_with_metadata(first_data, second_data):
    return compare_image_pair(first_data, second_data)


def compare_images(first_data, second_data):
    result, _, _ = compare_image_pair(first_data, second_data)
    return result

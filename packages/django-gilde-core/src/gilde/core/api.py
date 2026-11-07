"""What the Gilde apps' REST APIs share: checking a request's body, a page form's errors as the API's, and
a person as the APIs show them."""

from rest_framework.exceptions import ValidationError

from gilde.core import people


def validated(serializer_class, request, **kwargs) -> dict:
    """The request body, checked by `serializer_class`, refusing fields it does not know."""
    serializer = serializer_class(data=request.data, **kwargs)
    unknown = sorted(set(request.data) - set(serializer.fields))
    if unknown:
        raise ValidationError({'unknown_fields': unknown})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def form_errors(form) -> ValidationError:
    """A page form's errors as a 400; errors not tied to a field come under "detail"."""
    errors = form.errors.get_json_data()
    return ValidationError(
        {('detail' if name == '__all__' else name): [e['message'] for e in field] for name, field in errors.items()},
    )


def person(user) -> dict | None:
    """A person as the APIs show them: by their handle, as @-mentions name them, with their email address
    beside it when they have one."""
    return {'name': people.name(user), 'handle': people.handle(user), 'email': people.email(user)} if user else None

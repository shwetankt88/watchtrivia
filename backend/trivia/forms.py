from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from trivia.services.quota import get_profile


class WatchHistoryUploadForm(forms.Form):
    """Validates a Google Takeout watch-history.json upload.

    A plain Form, not a ModelForm: we are not creating a single model
    instance here, we are validating a file and then bulk-creating hundreds
    of rows from it.
    """

    file = forms.FileField(
        label="watch-history.json",
        help_text=(
            "Export your data from Google Takeout, then unzip it and upload "
            "the watch-history.json file from the YouTube folder."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        limit = settings.MAX_UPLOAD_BYTES

        if uploaded.size > limit:
            raise forms.ValidationError(
                f"That file is {uploaded.size / 1024 / 1024:.1f} MB. "
                f"The limit is {limit / 1024 / 1024:.0f} MB."
            )

        name = (uploaded.name or "").lower()
        if not name.endswith(".json"):
            raise forms.ValidationError(
                "That does not look like a .json file. Takeout archives are "
                "zipped — unzip it first, then upload the .json inside."
            )

        return uploaded


class SignupForm(forms.Form):
    """Self-service account creation, with the password rules from settings.

    A plain Form rather than UserCreationForm because there is no model here to
    save: the view builds the user, so this only has to validate and normalise
    the input. Two things it does that the stock form does not:

    * email is required and unique, because password resets are sent by email
      and a duplicate address silently takes over the account;
    * the honeypot field below, which is the cheapest spam filter available for
      a public signup form.
    """

    username = forms.CharField(
        max_length=150,
        help_text="Letters, digits and @/./+/-/_ only.",
    )
    email = forms.EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(
        widget=forms.PasswordInput, label="Password again"
    )
    # Bots fill in every input they find. A real person, who cannot see this
    # field because it is hidden with CSS, never touches it.
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account already exists for that email address."
            )
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two passwords do not match.")
        if password2:
            # A plain Form gets none of AUTH_PASSWORD_VALIDATORS for free. On a
            # public signup form that means "password" would be accepted, so the
            # settings validators are run explicitly against the candidate user.
            candidate = User(
                username=self.cleaned_data.get("username") or "",
                email=self.cleaned_data.get("email") or "",
            )
            try:
                validate_password(password2, user=candidate)
            except forms.ValidationError as exc:
                raise forms.ValidationError(exc.messages) from exc
        return password2

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Registration failed. Please try again.")
        return ""

    def save(self):
        """Create the user and their profile, then return the user.

        Both rows go in one transaction: a user without a profile is a user
        whose quota and theme settings do not exist, which is exactly the kind
        of half-built state `Profile` was designed to avoid.
        """
        with transaction.atomic():
            user = User.objects.create_user(
                username=self.cleaned_data["username"],
                email=self.cleaned_data["email"],
                password=self.cleaned_data["password1"],
            )
            get_profile(user)
        return user


class LoginForm(AuthenticationForm):
    """The stock login form, with the username normalised.

    `username` is left as typed so a wrong password gives the same message as
    an unknown user, but the surrounding whitespace people paste in is dropped
    first, because "alice " failing while "alice" works looks like a bug.
    """

    def clean_username(self):
        return self.cleaned_data["username"].strip()


class AnswerForm(forms.Form):
    """Validates one submitted answer against a specific question's options.

    Not a ModelForm either: the choice set is dynamic, because it comes from
    the question's JSONField rather than from a fixed list in the model.
    """

    def __init__(self, *args, question, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        self.fields["selected_answer"] = forms.ChoiceField(
            choices=[(opt, opt) for opt in question.options],
            widget=forms.RadioSelect,
            label="Your answer",
        )

    def clean_selected_answer(self):
        return self.cleaned_data["selected_answer"]

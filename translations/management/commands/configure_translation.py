from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from translations.gateway import GatewayError, validate_configuration
from translations.models import SystemConfiguration


class Command(BaseCommand):
    help = 'Explicitly provision the singleton Gateway translation configuration (no model calls).'

    def add_arguments(self, parser):
        parser.add_argument('--target-language-code', required=True)
        parser.add_argument('--target-language-name', required=True)
        parser.add_argument('--translation-model', required=True)
        parser.add_argument('--post-editing-model', required=True)
        parser.add_argument('--retrieved-sentences', type=int, default=5)

    @transaction.atomic
    def handle(self, *args, **options):
        configuration = SystemConfiguration.objects.select_for_update().first() or SystemConfiguration()
        configuration.target_language_code = options['target_language_code']
        configuration.target_language_name = options['target_language_name']
        configuration.translation_model = options['translation_model']
        configuration.post_editing_model = options['post_editing_model']
        configuration.num_sentences_retrieved = options['retrieved_sentences']
        configuration.dspy_config = None
        configuration.translation_prompt = (
            f'You are a linguist helping to post-edit translations from English to {configuration.target_language_name}. '
            'Correct the candidate translations using supplied examples and glossary entries. '
            'Return only the corrected translation.'
        )
        try:
            configuration.full_clean()
            validate_configuration(configuration)
        except Exception as error:
            if isinstance(error, GatewayError):
                raise CommandError(error.code) from None
            raise CommandError('Invalid translation configuration.') from None
        configuration.save()
        self.stdout.write(self.style.SUCCESS(f'Configuration ready: id={configuration.pk}'))

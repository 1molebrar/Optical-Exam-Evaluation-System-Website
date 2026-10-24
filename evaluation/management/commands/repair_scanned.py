import os
from django.core.management.base import BaseCommand
from evaluation.models import ScannedPaper


class Command(BaseCommand):
    help = 'Find and repair ScannedPaper records with missing/corrupt image files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Delete broken records instead of just listing them',
        )
        parser.add_argument(
            '--reprocess',
            action='store_true',
            help='Reset broken records to pending for re-upload',
        )

    def handle(self, *args, **options):
        broken = []
        for p in ScannedPaper.objects.all():
            try:
                path = p.image.path
                if not os.path.isfile(path):
                    broken.append(p)
            except Exception:
                broken.append(p)

        self.stdout.write(f'Total scanned papers: {ScannedPaper.objects.count()}')
        self.stdout.write(f'Broken records: {len(broken)}')

        if not broken:
            self.stdout.write(self.style.SUCCESS('No broken records found.'))
            return

        for p in broken:
            try:
                path = p.image.path
            except Exception as e:
                path = f'<error: {e}>'
            self.stdout.write(f'  ID={p.id} name={p.image.name} status={p.status} path={path}')

        if options['delete']:
            count = 0
            for p in broken:
                p.delete()
                count += 1
            self.stdout.write(self.style.SUCCESS(f'Deleted {count} broken records.'))

        elif options['reprocess']:
            count = 0
            for p in broken:
                p.status = 'pending'
                p.processed = False
                p.save(update_fields=['status', 'processed'])
                count += 1
            self.stdout.write(self.style.SUCCESS(
                f'Reset {count} records to pending for re-upload.'
            ))

        else:
            self.stdout.write(self.style.WARNING(
                'Run with --delete to remove broken records or --reprocess to reset them.'
            ))

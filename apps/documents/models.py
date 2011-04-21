import os
from datetime import datetime
import sys
import tempfile

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q
from django.contrib.auth.models import User

from python_magic import magic

from dynamic_search.api import register
from converter.api import get_page_count

from documents.conf.settings import AVAILABLE_INDEXING_FUNCTIONS
from documents.conf.settings import AVAILABLE_FUNCTIONS
from documents.conf.settings import AVAILABLE_MODELS
from documents.conf.settings import CHECKSUM_FUNCTION
from documents.conf.settings import UUID_FUNCTION
from documents.conf.settings import STORAGE_BACKEND
from documents.conf.settings import AVAILABLE_TRANSFORMATIONS
from documents.conf.settings import DEFAULT_TRANSFORMATIONS
from documents.conf.settings import RECENT_COUNT


def get_filename_from_uuid(instance, filename):
    filename, extension = os.path.splitext(filename)
    instance.file_filename = filename
    #remove prefix '.'
    instance.file_extension = extension[1:]
    uuid = UUID_FUNCTION()
    instance.uuid = uuid
    return uuid


class DocumentType(models.Model):
    name = models.CharField(max_length=32, verbose_name=_(u'name'))

    def __unicode__(self):
        return self.name


class Document(models.Model):
    ''' Minimum fields for a document entry.
    '''
    document_type = models.ForeignKey(DocumentType, verbose_name=_(u'document type'))
    file = models.FileField(upload_to=get_filename_from_uuid, storage=STORAGE_BACKEND(), verbose_name=_(u'file'))
    uuid = models.CharField(max_length=48, default=UUID_FUNCTION(), blank=True, editable=False)
    file_mimetype = models.CharField(max_length=64, default='', editable=False)
    file_mime_encoding = models.CharField(max_length=64, default='', editable=False)
    #FAT filename can be up to 255 using LFN
    file_filename = models.CharField(max_length=255, default='', editable=False, db_index=True)
    file_extension = models.CharField(max_length=16, default='', editable=False, db_index=True)
    date_added = models.DateTimeField(verbose_name=_(u'added'), auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(verbose_name=_(u'updated'), auto_now=True)
    checksum = models.TextField(blank=True, null=True, verbose_name=_(u'checksum'), editable=False)
    description = models.TextField(blank=True, null=True, verbose_name=_(u'description'), db_index=True)

    class Meta:
        verbose_name = _(u'document')
        verbose_name_plural = _(u'documents')
        ordering = ['-date_added']

    def __unicode__(self):
        return '%s.%s' % (self.file_filename, self.file_extension)

    def save(self, *args, **kwargs):
        new_document = not self.pk

        super(Document, self).save(*args, **kwargs)

        if new_document:
            #Only do this for new documents
            self.update_checksum(save=False)
            self.update_mimetype(save=False)
            self.save()
            self.update_page_count(save=False)
            self.apply_default_transformations()

    @models.permalink
    def get_absolute_url(self):
        return ('document_view_simple', [self.id])

    def get_fullname(self):
        return os.extsep.join([self.file_filename, self.file_extension])

    def update_mimetype(self, save=True):
        if self.exists():
            try:
                source = self.open()
                mime = magic.Magic(mime=True)
                self.file_mimetype = mime.from_buffer(source.read())
                source.seek(0)
                mime_encoding = magic.Magic(mime_encoding=True)
                self.file_mime_encoding = mime_encoding.from_buffer(source.read())
            except:
                self.file_mimetype = u''
                self.file_mime_encoding = u''
            finally:
                if source:
                    source.close()
                if save:
                    self.save()

    def open(self):
        return self.file.storage.open(self.file.path)

    def update_checksum(self, save=True):
        if self.exists():
            source = self.open()
            self.checksum = unicode(CHECKSUM_FUNCTION(source.read()))
            source.close()
            if save:
                self.save()

    def update_page_count(self, save=True):
        handle, filepath = tempfile.mkstemp()
        self.save_to_file(filepath)
        detected_pages = get_page_count(filepath)
        os.close(handle)
        try:
            os.remove(filepath)
        except OSError:
            pass

        current_pages = DocumentPage.objects.filter(document=self).order_by('page_number',)
        if current_pages.count() > detected_pages:
            for page in current_pages[detected_pages:]:
                page.delete()

        for page_number in range(detected_pages):
            DocumentPage.objects.get_or_create(
                document=self, page_number=page_number + 1)

        if save:
            self.save()

        return detected_pages

    def save_to_file(self, filepath, buffer_size=1024 * 1024):
        input_descriptor = self.open()
        output_descriptor = open(filepath, 'wb')
        while True:
            copy_buffer = input_descriptor.read(buffer_size)
            if copy_buffer:
                output_descriptor.write(copy_buffer)
            else:
                break

        output_descriptor.close()
        input_descriptor.close()
        return filepath

    def exists(self):
        return self.file.storage.exists(self.file.path)
        
    def get_metadata_string(self):
        return u', '.join([u'%s - %s' % (metadata.metadata_type, metadata.value) for metadata in self.documentmetadata_set.select_related('metadata_type', 'document').defer('document__document_type', 'document__file', 'document__description', 'document__file_filename', 'document__uuid', 'document__date_added', 'document__date_updated', 'document__file_mimetype', 'document__file_mime_encoding')])

    def get_metadata_groups(self):
        errors = []
        metadata_groups = {}
        if MetadataGroup.objects.all().count():
            metadata_dict = {}
            for document_metadata in self.documentmetadata_set.all():
                metadata_dict['metadata_%s' % document_metadata.metadata_type.name] = document_metadata.value

            for group in MetadataGroup.objects.filter((Q(document_type=self.document_type) | Q(document_type=None)) & Q(enabled=True)):
                total_query = Q()
                for item in group.metadatagroupitem_set.filter(enabled=True):
                    try:
                        value_query = Q(**{'value__%s' % item.operator: eval(item.expression, metadata_dict)})
                        if item.negated:
                            query = (Q(metadata_type__id=item.metadata_type_id) & ~value_query)
                        else:
                            query = (Q(metadata_type__id=item.metadata_type_id) & value_query)

                        if item.inclusion == INCLUSION_AND:
                            total_query &= query
                        elif item.inclusion == INCLUSION_OR:
                            total_query |= query
                    except Exception, e:
                        errors.append(e)
                        value_query = Q()
                        query = Q()

                if total_query:
                    document_id_list = DocumentMetadata.objects.filter(total_query).values_list('document', flat=True)
                else:
                    document_id_list = []
                metadata_groups[group] = Document.objects.filter(Q(id__in=document_id_list)).order_by('file_filename') or []
        return metadata_groups, errors

    def apply_default_transformations(self):
        #Only apply default transformations on new documents
        if DEFAULT_TRANSFORMATIONS and reduce(lambda x, y: x + y, [page.documentpagetransformation_set.count() for page in self.documentpage_set.all()]) == 0:
            for transformation in DEFAULT_TRANSFORMATIONS:
                if 'name' in transformation:
                    for document_page in self.documentpage_set.all():
                        page_transformation = DocumentPageTransformation(
                            document_page=document_page,
                            order=0,
                            transformation=transformation['name'])
                        if 'arguments' in transformation:
                            page_transformation.arguments = transformation['arguments']

                        page_transformation.save()

available_functions_string = (_(u' Available functions: %s') % ','.join(['%s()' % name for name, function in AVAILABLE_FUNCTIONS.items()])) if AVAILABLE_FUNCTIONS else ''
available_models_string = (_(u' Available models: %s') % ','.join([name for name, model in AVAILABLE_MODELS.items()])) if AVAILABLE_MODELS else ''


class MetadataType(models.Model):
    name = models.CharField(max_length=48, verbose_name=_(u'name'), help_text=_(u'Do not use python reserved words.'))
    title = models.CharField(max_length=48, verbose_name=_(u'title'), blank=True, null=True)
    default = models.CharField(max_length=128, blank=True, null=True,
        verbose_name=_(u'default'),
        help_text=_(u'Enter a string to be evaluated.%s') % available_functions_string)
    lookup = models.CharField(max_length=128, blank=True, null=True,
        verbose_name=_(u'lookup'),
        help_text=_(u'Enter a string to be evaluated.  Example: [user.get_full_name() for user in User.objects.all()].%s') % available_models_string)
    #TODO: datatype?

    def __unicode__(self):
        return self.title if self.title else self.name

    class Meta:
        verbose_name = _(u'metadata type')
        verbose_name_plural = _(u'metadata types')


class DocumentTypeMetadataType(models.Model):
    document_type = models.ForeignKey(DocumentType, verbose_name=_(u'document type'))
    metadata_type = models.ForeignKey(MetadataType, verbose_name=_(u'metadata type'))
    required = models.BooleanField(default=True, verbose_name=_(u'required'))
    #TODO: override default for this document type

    def __unicode__(self):
        return unicode(self.metadata_type)

    class Meta:
        verbose_name = _(u'document type metadata type connector')
        verbose_name_plural = _(u'document type metadata type connectors')


available_indexing_functions_string = (_(u' Available functions: %s') % ','.join(['%s()' % name for name, function in AVAILABLE_INDEXING_FUNCTIONS.items()])) if AVAILABLE_INDEXING_FUNCTIONS else ''


class MetadataIndex(models.Model):
    document_type = models.ForeignKey(DocumentType, verbose_name=_(u'document type'))
    expression = models.CharField(max_length=128,
        verbose_name=_(u'indexing expression'),
        help_text=_(u'Enter a python string expression to be evaluated.  The slash caracter "/" acts as a directory delimiter.%s') % available_indexing_functions_string)
    enabled = models.BooleanField(default=True, verbose_name=_(u'enabled'))

    def __unicode__(self):
        return unicode(self.expression)

    class Meta:
        verbose_name = _(u'metadata index')
        verbose_name_plural = _(u'metadata indexes')


class DocumentMetadata(models.Model):
    document = models.ForeignKey(Document, verbose_name=_(u'document'))
    metadata_type = models.ForeignKey(MetadataType, verbose_name=_(u'metadata type'))
    value = models.TextField(blank=True, null=True, verbose_name=_(u'metadata value'), db_index=True)

    def __unicode__(self):
        return unicode(self.metadata_type)

    class Meta:
        verbose_name = _(u'document metadata')
        verbose_name_plural = _(u'document metadata')


class DocumentTypeFilename(models.Model):
    document_type = models.ForeignKey(DocumentType, verbose_name=_(u'document type'))
    filename = models.CharField(max_length=128, verbose_name=_(u'filename'), db_index=True)
    enabled = models.BooleanField(default=True, verbose_name=_(u'enabled'))

    def __unicode__(self):
        return self.filename

    class Meta:
        ordering = ['filename']
        verbose_name = _(u'document type quick rename filename')
        verbose_name_plural = _(u'document types quick rename filenames')


class DocumentPage(models.Model):
    document = models.ForeignKey(Document, verbose_name=_(u'document'))
    content = models.TextField(blank=True, null=True, verbose_name=_(u'content'), db_index=True)
    page_label = models.CharField(max_length=32, blank=True, null=True, verbose_name=_(u'page label'))
    page_number = models.PositiveIntegerField(default=1, editable=False, verbose_name=_(u'page number'), db_index=True)

    def __unicode__(self):
        return _(u'Page %(page_num)d of %(document)s') % {
            'document': unicode(self.document), 'page_num': self.page_number}

    class Meta:
        ordering = ['page_number']
        verbose_name = _(u'document page')
        verbose_name_plural = _(u'document pages')

    @models.permalink
    def get_absolute_url(self):
        return ('document_page_view', [self.id])


class MetadataGroup(models.Model):
    document_type = models.ManyToManyField(DocumentType, null=True, blank=True,
        verbose_name=_(u'document type'), help_text=_(u'If left blank, all document types will be matched.'))
    name = models.CharField(max_length=32, verbose_name=_(u'name'))
    label = models.CharField(max_length=32, verbose_name=_(u'label'))
    enabled = models.BooleanField(default=True, verbose_name=_(u'enabled'))

    def __unicode__(self):
        return self.label if self.label else self.name

    class Meta:
        verbose_name = _(u'metadata document group')
        verbose_name_plural = _(u'metadata document groups')


INCLUSION_AND = u'&'
INCLUSION_OR = u'|'

INCLUSION_CHOICES = (
    (INCLUSION_AND, _(u'and')),
    (INCLUSION_OR, _(u'or')),
)

OPERATOR_CHOICES = (
    (u'exact', _(u'is equal')),
    (u'iexact', _(u'is equal (case insensitive)')),
    (u'contains', _(u'contains')),
    (u'icontains', _(u'contains (case insensitive)')),
    (u'in', _(u'is in')),
    (u'gt', _(u'is greater than')),
    (u'gte', _(u'is greater than or equal')),
    (u'lt', _(u'is less than')),
    (u'lte', _(u'is less than or equal')),
    (u'startswith', _(u'starts with')),
    (u'istartswith', _(u'starts with (case insensitive)')),
    (u'endswith', _(u'ends with')),
    (u'iendswith', _(u'ends with (case insensitive)')),
    (u'regex', _(u'is in regular expression')),
    (u'iregex', _(u'is in regular expression (case insensitive)')),
)


class MetadataGroupItem(models.Model):
    metadata_group = models.ForeignKey(MetadataGroup, verbose_name=_(u'metadata group'))
    inclusion = models.CharField(default=INCLUSION_AND, max_length=16, choices=INCLUSION_CHOICES, help_text=_(u'The inclusion is ignored for the first item.'))
    metadata_type = models.ForeignKey(MetadataType, verbose_name=_(u'metadata type'), help_text=_(u'This represents the metadata of all other documents.'))
    operator = models.CharField(max_length=16, choices=OPERATOR_CHOICES)
    expression = models.CharField(max_length=128,
        verbose_name=_(u'expression'), help_text=_(u'This expression will be evaluated against the current selected document.  The document metadata is available as variables of the same name but with the "metadata_" prefix added their name.'))
    negated = models.BooleanField(default=False, verbose_name=_(u'negated'), help_text=_(u'Inverts the logic of the operator.'))
    enabled = models.BooleanField(default=True, verbose_name=_(u'enabled'))

    def __unicode__(self):
        return u'[%s] %s %s %s %s %s' % (u'x' if self.enabled else u' ', self.get_inclusion_display(), self.metadata_type, _(u'not') if self.negated else u'', self.get_operator_display(), self.expression)

    class Meta:
        verbose_name = _(u'metadata group item')
        verbose_name_plural = _(u'metadata group items')


available_transformations = ([(name, data['label']) for name, data in AVAILABLE_TRANSFORMATIONS.items()]) if AVAILABLE_MODELS else []


class DocumentPageTransformation(models.Model):
    document_page = models.ForeignKey(DocumentPage, verbose_name=_(u'document page'))
    order = models.PositiveIntegerField(default=0, blank=True, null=True, verbose_name=_(u'order'), db_index=True)
    transformation = models.CharField(choices=available_transformations, max_length=128, verbose_name=_(u'transformation'))
    arguments = models.TextField(blank=True, null=True, verbose_name=_(u'arguments'), help_text=_(u'Use dictionaries to indentify arguments, example: {\'degrees\':90}'))

    def __unicode__(self):
        return u'"%s" for %s' % (self.get_transformation_display(), unicode(self.document_page))

    class Meta:
        ordering = ('order',)
        verbose_name = _(u'document page transformation')
        verbose_name_plural = _(u'document page transformations')


class RecentDocumentManager(models.Manager):
    def add_document_for_user(self, user, document):
        new_recent, _ = RecentDocument.objects.get_or_create(user=user, document=document, defaults={'datetime_accessed': datetime.now()})
        new_recent.datetime_accessed = datetime.now()
        new_recent.save()
        to_delete = RecentDocument.objects.filter(user=user)[RECENT_COUNT:]
        for recent_to_delete in to_delete:
            recent_to_delete.delete()


class RecentDocument(models.Model):
    user = models.ForeignKey(User, verbose_name=_(u'user'), editable=False)
    document = models.ForeignKey(Document, verbose_name=_(u'document'), editable=False)
    datetime_accessed = models.DateTimeField(verbose_name=_(u'accessed'), db_index=True)
    
    objects = RecentDocumentManager()
    
    def __unicode__(self):
        return unicode(self.document)

    class Meta:
        ordering = ('-datetime_accessed',)
        verbose_name = _(u'recent document')
        verbose_name_plural = _(u'recent documents')


register(Document, _(u'document'), ['document_type__name', 'file_mimetype', 'file_filename', 'file_extension', 'documentmetadata__value', 'documentpage__content', 'description'])
#register(Document, _(u'document'), ['document_type__name', 'file_mimetype', 'file_extension', 'documentmetadata__value', 'documentpage__content', 'description', {'field_name':'file_filename', 'comparison':'iexact'}])

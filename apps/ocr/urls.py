from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('ocr.views',
    url(r'^log/$', 'ocr_log', (), 'ocr_log'),

    url(r'^processing/enable/$', 'ocr_enable', (), 'ocr_enable'),
    url(r'^processing/disable/$', 'ocr_disable', (), 'ocr_disable'),
    
    url(r'^document/(?P<document_id>\d+)/submit/$', 'submit_document', (), 'submit_document'),
    url(r'^document/multiple/submit/$', 'submit_document_multiple', (), 'submit_document_multiple'),
    url(r'^queue/document/(?P<queue_document_id>\d+)/delete/$', 'queue_document_delete', (), 'queue_document_delete'),
    url(r'^queue/document/multiple/delete/$', 'queue_document_multiple_delete', (), 'queue_document_multiple_delete'),
    url(r'^queue/document/(?P<queue_document_id>\d+)/re-queue/$', 're_queue_document', (), 're_queue_document'),
    url(r'^queue/document/multiple/re-queue/$', 're_queue_multiple_document', (), 're_queue_multiple_document'),


    url(r'^document/all/clean_up/$', 'all_document_ocr_cleanup', (), 'all_document_ocr_cleanup'),

    url(r'^queue/(?P<document_queue_id>\d+)/transformation/list/$', 'setup_queue_transformation_list', (), 'setup_queue_transformation_list'),
    url(r'^queue/(?P<document_queue_id>\w+)/transformation/create/$', 'setup_queue_transformation_create', (), 'setup_queue_transformation_create'),
    url(r'^queue/transformation/(?P<transformation_id>\w+)/edit/$', 'setup_queue_transformation_edit', (), 'setup_queue_transformation_edit'),
    url(r'^queue/transformation/(?P<transformation_id>\w+)/delete/$', 'setup_queue_transformation_delete', (), 'setup_queue_transformation_delete'),
)

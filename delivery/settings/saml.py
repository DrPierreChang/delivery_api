import os

import saml2

TEST_SAML_KEYS = {
    'encryption_private': 'conf/saml/test_keys/encryption_private.pem',
    'encryption_public': 'conf/saml/test_keys/encryption_public.pem',
    'signing_private': 'conf/saml/test_keys/signing_private.pem',
    'signing_public': 'conf/saml/test_keys/signing_public.pem',
}


class KeyPath:
    def __init__(self, saml_keys, base_dir):
        self.base_dir = base_dir
        self.saml_keys = saml_keys

    def path(self, key):
        return os.path.join(self.base_dir, self.saml_keys[key])


def build_saml_config(base_dir, base_url, env_vars):
    saml_keys = getattr(env_vars, 'SAML_KEYS', TEST_SAML_KEYS)
    key_path_getter = KeyPath(saml_keys, base_dir)

    return {
        'xmlsec_binary': '/usr/bin/xmlsec1',
        'entityid': '{base_url}/saml2/metadata'.format(base_url=base_url),
        'attribute_map_dir': os.path.join(base_dir, 'custom_auth/saml2'),
        'allow_unknown_attributes': True,
        'service': {
            'sp': {
                'name': '{cluster_name} SP'.format(cluster_name=env_vars.CLUSTER_NAME),
                'name_id_format': [
                    'urn:oasis:names:tc:SAML:2.0:nameid-format:transient',
                    'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
                ],

                'allow_unsolicited': True,
                'endpoints': {
                    'assertion_consumer_service': [
                        ('{base_url}/saml2/acs/'.format(base_url=base_url),
                         saml2.BINDING_HTTP_POST),
                    ],
                },
                'force_authn': True,
                'required_attributes': ['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'],
                'want_response_signed': False,
                'idp': {
                    'https://corpsts.miele.com/adfs/services/trust': {
                        'single_sign_on_service': {
                            saml2.BINDING_HTTP_REDIRECT: 'https://corpsts.miele.com/adfs/ls/',
                        },
                        'single_logout_service': {
                            saml2.BINDING_HTTP_REDIRECT: 'https://corpsts.miele.com/adfs/ls/',
                        },
                    },
                },
            },
        },

        'metadata': {
            'remote': [
                {'url': 'https://corpsts.miele.com/FederationMetadata/2007-06/FederationMetadata.xml',
                 'disable_ssl_certificate_validation': True},
            ],
        },

        'debug': 1,

        'key_file': key_path_getter.path('signing_private'),
        'cert_file': key_path_getter.path('signing_public'),

        'encryption_keypairs': [{
            'key_file': key_path_getter.path('encryption_private'),
            'cert_file': key_path_getter.path('encryption_public'),
        }],
    }

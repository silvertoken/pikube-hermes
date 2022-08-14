import kopf
import logging
import kubernetes.config as kconfig
import kubernetes.client as kclient

hermes_crd = kclient.V1CustomResourceDefinition(
    api_version="apiextensions.k8s.io/v1",
    kind="CustomResourceDefinition",
    metadata=kclient.V1ObjectMeta(name="hermes.operators.silvertoken.github.io"),
    spec=kclient.V1CustomResourceDefinitionSpec(
        group="operators.silvertoken.github.io",
        versions=[kclient.V1CustomResourceDefinitionVersion(
            name="v1",
            served=True,
            storage=True,
            schema=kclient.V1CustomResourceValidation(
                open_apiv3_schema=kclient.V1JSONSchemaProps(
                    type="object",
                    properties={
                        "spec": kclient.V1JSONSchemaProps(
                            type="object",
                            properties = {
                                "image": kclient.V1JSONSchemaProps(type="string")
							}
                        ),
                        "status": kclient.V1JSONSchemaProps(
                            type="object",
                            x_kubernetes_preserve_unknown_fields=True
                        )
                    }
                )
            )
        )],
        scope="Namespaced",
        names=kclient.V1CustomResourceDefinitionNames(
            plural="hermes",
            singular="hermes",
            kind="Hermes",
            short_names=["hermes"]
        )
    )
)

try:
	kconfig.load_kube_config()
except kconfig.ConfigException:
	kconfig.load_incluster_config()

api = kclient.ApiextensionsV1Api()
try:
	api.create_custom_resource_definition(hermes_crd)
except kclient.rest.ApiException as e:
	if e.status == 409:
		print("CRD already exists")
	else:
		raise e

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.peering.name = "hermes"
    settings.peering.mandatory = True
    
@kopf.on.create('operators.silvertoken.github.io', 'v1', 'hermes')
def on_hermes_create(namespace, spec, body, **kwargs):
	logging.debug(f"Hermes create handler is called: {body}")

	app = kclient.AppsV1Api()
	core = kclient.CoreV1Api()

	depList = app.list_namespaced_deployment(namespace=namespace, label_selector='app={}'.format(body.metadata.name))
	logging.debug("Found {d} deployments named '{n}'".format(d=len(depList.items), n=body.metadata.name))
	if len(depList.items) == 0:
		logging.info(f"Creating a new hermes deployment in namespace '{namespace}' with name: {body.metadata.name}")
		dep = gen_hermes_deployment(namespace, body.metadata.name, spec)
		logging.debug(f"Generated deployment: {dep}")
		try:
			response = app.create_namespaced_deployment(namespace=namespace, body=dep)
			logging.debug(f"Created deployment: {response}")
   
		except kclient.ApiException as e:
			logging.error("Exception calling create '{}'".format(e))
			raise kopf.PermanentError("Exception calling create '{}'".format(e))
				
			
def gen_hermes_deployment(namespace, name, spec):
    dep = kclient.V1Deployment(
		metadata = kclient.V1ObjectMeta(namespace=namespace, name=name),
		spec = kclient.V1DeploymentSpec(
			selector = kclient.V1LabelSelector(match_labels={"app": name}),
			template = kclient.V1PodTemplateSpec(
				metadata = kclient.V1ObjectMeta(labels={"app": name}),
				spec =  kclient.V1PodSpec(
					containers = [kclient.V1Container(
						name = "hermes",
						image = spec.get('image'),
						env = [
							kclient.V1EnvVar(
           						name="DISCORD_TOKEN", 
                 				value_from=kclient.V1EnvVarSource(
									secret_key_ref = kclient.V1SecretKeySelector(
										name = "discord-token",
										key = "DISCORD_TOKEN"
									)
								))
						]
					)]
				)
			)
		),
	)
    kopf.adopt(dep)
    return dep
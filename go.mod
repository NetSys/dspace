module digi.dev/digivice

go 1.13

require (
	github.com/banzaicloud/k8s-objectmatcher v1.4.1
	github.com/slok/kubewebhook v0.10.0
	github.com/spf13/cobra v1.0.0
	github.com/stretchr/testify v1.5.1
	github.com/tidwall/sjson v1.1.1
	github.com/xlab/treeprint v1.0.0
	k8s.io/api v0.18.6
	k8s.io/apimachinery v0.18.6
	k8s.io/client-go v12.0.0+incompatible
	sigs.k8s.io/controller-runtime v0.6.3
)

replace k8s.io/client-go => k8s.io/client-go v0.18.2

package core

import (
	"fmt"
	"strings"

	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
)

const (
	DefaultNamespace = "default"

	UriSeparator      = types.Separator
	AttrPathSeparator = '.'
)

// Kind identifies a model schema, e.g., digi.dev/v1/Lamp; it is a re-declaration of
// https://godoc.org/k8s.io/apimachinery/pkg/runtime/schema#GroupVersionResource with json tags and field name changes.
type Kind struct {
	// Model schema group
	Group string `json:"group,omitempty"`
	// Schema version
	Version string `json:"version,omitempty"`
	// Schema name; first letter capitalized, e.g., Roomba
	Name string `json:"name,omitempty"`
}

func (k *Kind) Plural() string {
	// XXX allow reading plural from input or define a conversion rule
	return strings.ToLower(k.Name) + "s"
}

func (k *Kind) Gvk() schema.GroupVersionKind {
	return schema.GroupVersionKind{
		Group:   k.Group,
		Version: k.Version,
		Kind:    k.Name,
	}
}

func (k *Kind) Gvr() schema.GroupVersionResource {
	return schema.GroupVersionResource{
		Group:    k.Group,
		Version:  k.Version,
		Resource: k.Plural(),
	}
}

func (k *Kind) String() string {
	return k.Gvk().String()
}

// Auri identifies a set of attributes belonging to a model on the semantic message bus
// E.g., /digi.dev/v1/Roomba/default/roomba-foo.power
type Auri struct {
	// model schema
	Kind Kind `json:"kind,omitempty"`
	// name of the model
	Name string `json:"name,omitempty"`
	// namespace of the model
	Namespace string `json:"namespace,omitempty"`
	// path to attribute(s) in the model; if path empty, Auri points to the model
	Path string `json:"path,omitempty"`
}

func (ar *Auri) Gvr() schema.GroupVersionResource {
	return ar.Kind.Gvr()
}

func (ar *Auri) Gvk() schema.GroupVersionKind {
	return ar.Kind.Gvk()
}

func (ar *Auri) SpacedName() types.NamespacedName {
	return types.NamespacedName{
		Name:      ar.Name,
		Namespace: ar.Namespace,
	}
}

func (ar *Auri) String() string {
	if ar.Path == "" {
		return fmt.Sprintf("%s%c%s", ar.Gvr().String(), UriSeparator, ar.SpacedName().String())
	}
	return fmt.Sprintf("%s%c%s%c%s", ar.Gvr().String(), UriSeparator, ar.SpacedName().String(), AttrPathSeparator, strings.TrimLeft(ar.Path, fmt.Sprintf("%c", AttrPathSeparator)))
}

func AttrPathSlice(p string) []string {
	sep := fmt.Sprintf("%c", AttrPathSeparator)
	// leading dots in the attribute path is optional
	return strings.Split(strings.TrimLeft(p, sep), sep)
}

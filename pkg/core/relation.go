package core

const (
	MountAttrPath = ".spec.mounts"

	MountModeAttrPath = ".mode"
	DefaultMountMode   = "expose"

	MountStatusAttrPath = ".status"
	MountActiveStatus    = "active"
	MountInactiveStatus  = "inactive"
)

var (
	MountAttrPathSlice = AttrPathSlice(MountAttrPath)
	_                  = MountAttrPathSlice
)

type Mount struct {
	Source Auri `json:"source,omitempty"`
	Target Auri `json:"target,omitempty"`

	Mode   string `json:"mode,omitempty"`
	Status string `json:"status,omitempty"`
}

// mounts indexed by the target's namespaced name
type MountRefs map[string]*Mount